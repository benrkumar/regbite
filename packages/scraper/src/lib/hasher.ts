import { createHash } from 'crypto';

export function hashDocument(content: string): string {
  return createHash('sha256').update(content, 'utf-8').digest('hex');
}

export function hashBuffer(buf: Buffer): string {
  return createHash('sha256').update(buf).digest('hex');
}
