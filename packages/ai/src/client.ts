import Anthropic from "@anthropic-ai/sdk";

let client: Anthropic | null = null;

export function createAnthropicClient(): Anthropic {
  if (!client) {
    client = new Anthropic();
  }
  return client;
}
