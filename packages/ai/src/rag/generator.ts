/**
 * RAG generator — Claude Sonnet + retrieved FDA context
 *
 * Takes a prompt + retrieved documents and generates a structured response
 * using Claude Sonnet as the primary model (claude-sonnet-4-6).
 */

import { createAnthropicClient } from '../client.js';
import { retrieve } from './retriever.js';
import type { RetrievedDocument } from './retriever.js';
import {
  buildIngredientAnalysisPrompt,
  type IngredientAnalysisInput,
} from '../prompts/ingredient-analysis.js';
import {
  buildClaimsClassificationPrompt,
  type ClaimsClassificationInput,
} from '../prompts/claims-classification.js';
import { buildNDIGuidancePrompt, type NDIGuidanceInput } from '../prompts/ndi-guidance.js';
import { buildLabelReviewPrompt, type LabelReviewInput } from '../prompts/label-review.js';

const MODEL = 'claude-sonnet-4-6';
const MAX_TOKENS = 2048;

async function callClaude(prompt: string): Promise<string> {
  const anthropic = createAnthropicClient();
  const msg = await anthropic.messages.create({
    model: MODEL,
    max_tokens: MAX_TOKENS,
    messages: [{ role: 'user', content: prompt }],
  });

  const content = msg.content[0];
  if (content.type !== 'text') throw new Error('Unexpected response type from Claude');
  return content.text;
}

function parseJsonResponse<T>(text: string): T {
  // Extract JSON from markdown code block if wrapped
  const jsonMatch = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/) ?? text.match(/(\{[\s\S]*\})/);
  const jsonText = jsonMatch ? jsonMatch[1] : text;
  return JSON.parse(jsonText) as T;
}

// ── Public API ─────────────────────────────────────────────────────────────────

export async function analyzeIngredientWithRAG(
  input: IngredientAnalysisInput,
): Promise<Record<string, unknown>> {
  const query = `${input.ingredientName} FDA dietary supplement safety ${input.casNumber ?? ''}`;
  const context = await retrieve(query, 6).catch(() => [] as RetrievedDocument[]);

  const prompt = buildIngredientAnalysisPrompt({ ...input, context });
  const response = await callClaude(prompt);
  return parseJsonResponse(response);
}

export async function classifyClaimWithRAG(
  input: ClaimsClassificationInput,
): Promise<Record<string, unknown>> {
  const query = `FDA enforcement dietary supplement claim "${input.claim}"`;
  const enforcementContext = await retrieve(query, 4).catch(() => [] as RetrievedDocument[]);

  const prompt = buildClaimsClassificationPrompt({ ...input, enforcementContext });
  const response = await callClaude(prompt);
  return parseJsonResponse(response);
}

export async function getNDIGuidance(
  input: NDIGuidanceInput,
): Promise<Record<string, unknown>> {
  const prompt = buildNDIGuidancePrompt(input);
  const response = await callClaude(prompt);
  return parseJsonResponse(response);
}

export async function reviewLabel(
  input: LabelReviewInput,
): Promise<Record<string, unknown>> {
  const prompt = buildLabelReviewPrompt(input);
  const response = await callClaude(prompt);
  return parseJsonResponse(response);
}
