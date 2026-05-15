import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@regbite/database";
import { requireOrganizationId } from "@/lib/auth";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const orgId = await requireOrganizationId();
    const { id } = await params;

    const check = await prisma.complianceCheck.findFirst({
      where: { id, organizationId: orgId },
      include: {
        formulation: {
          select: {
            productName: true,
            productType: true,
            servingSize: true,
            ingredients: true,
            claims: true,
          },
        },
        organization: { select: { name: true, slug: true } },
      },
    });

    if (!check) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    if (check.status !== "COMPLETED") {
      return NextResponse.json(
        { error: "Check is not completed yet" },
        { status: 409 }
      );
    }

    const formulation = check.formulation;

    const report = {
      reportId: check.id,
      generatedAt: new Date().toISOString(),
      organization: check.organization,
      formulation: formulation
        ? {
            productName: formulation.productName,
            productType: formulation.productType,
            servingSize: formulation.servingSize,
            ingredients: formulation.ingredients,
            claims: formulation.claims,
          }
        : null,
      check: {
        id: check.id,
        checkType: check.checkType,
        status: check.status,
        overallScore: check.overallScore,
        results: check.results,
        regulatoryCitations: check.regulatoryCitations,
        createdAt: check.createdAt,
      },
    };

    // If R2 is configured, upload and return presigned URL
    const hasR2 =
      process.env.R2_ACCOUNT_ID &&
      process.env.R2_ACCESS_KEY_ID &&
      process.env.R2_SECRET_ACCESS_KEY &&
      process.env.R2_BUCKET_NAME;

    if (hasR2) {
      try {
        const { uploadToR2, getPresignedDownloadUrl } = await import("@regbite/config");
        const key = `reports/${check.organizationId}/${check.id}.json`;
        await uploadToR2(key, JSON.stringify(report, null, 2), "application/json");
        const url = await getPresignedDownloadUrl(key, 3600);
        return NextResponse.json({ url, expiresIn: 3600 });
      } catch (r2Err) {
        console.error("[pdf route] R2 upload failed, falling back to inline:", r2Err);
      }
    }

    // Fallback: return inline JSON with download header
    return new NextResponse(JSON.stringify(report, null, 2), {
      headers: {
        "Content-Type": "application/json",
        "Content-Disposition": `attachment; filename="report-${check.id}.json"`,
      },
    });
  } catch {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
}
