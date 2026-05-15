import {
  S3Client,
  PutObjectCommand,
  GetObjectCommand,
  DeleteObjectCommand,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

let _client: S3Client | null = null;

export function getR2Client(): S3Client {
  if (_client) return _client;

  const accountId = process.env.R2_ACCOUNT_ID;
  const accessKeyId = process.env.R2_ACCESS_KEY_ID;
  const secretAccessKey = process.env.R2_SECRET_ACCESS_KEY;

  if (!accountId || !accessKeyId || !secretAccessKey) {
    throw new Error("R2 credentials not configured (R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY required)");
  }

  _client = new S3Client({
    region: "auto",
    endpoint: `https://${accountId}.r2.cloudflarestorage.com`,
    credentials: { accessKeyId, secretAccessKey },
  });

  return _client;
}

export async function uploadToR2(
  key: string,
  body: string | Uint8Array | Buffer,
  contentType: string
): Promise<string> {
  const client = getR2Client();
  const bucket = process.env.R2_BUCKET_NAME;
  if (!bucket) throw new Error("R2_BUCKET_NAME not configured");

  await client.send(
    new PutObjectCommand({
      Bucket: bucket,
      Key: key,
      Body: body,
      ContentType: contentType,
    })
  );

  const accountId = process.env.R2_ACCOUNT_ID!;
  return `https://${accountId}.r2.cloudflarestorage.com/${bucket}/${key}`;
}

export async function getPresignedDownloadUrl(
  key: string,
  expiresIn = 3600
): Promise<string> {
  const client = getR2Client();
  const bucket = process.env.R2_BUCKET_NAME;
  if (!bucket) throw new Error("R2_BUCKET_NAME not configured");

  return getSignedUrl(
    client,
    new GetObjectCommand({ Bucket: bucket, Key: key }),
    { expiresIn }
  );
}

export async function deleteFromR2(key: string): Promise<void> {
  const client = getR2Client();
  const bucket = process.env.R2_BUCKET_NAME;
  if (!bucket) throw new Error("R2_BUCKET_NAME not configured");

  await client.send(
    new DeleteObjectCommand({ Bucket: bucket, Key: key })
  );
}
