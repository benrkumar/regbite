import { createClient } from 'redis';

let redisClient: ReturnType<typeof createClient> | null = null;

async function getRedis() {
  if (!redisClient || !redisClient.isOpen) {
    redisClient = createClient({ url: process.env.REDIS_URL });
    redisClient.on('error', (err) => console.error('[rate-limiter] Redis error:', err));
    await redisClient.connect();
  }
  return redisClient;
}

const PLAN_LIMITS: Record<string, number> = {
  STARTER: 50,
  GROWTH: 200,
  PROFESSIONAL: 9999,
  ENTERPRISE: 9999,
  CONSULTANT: 9999,
};

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  limit: number;
  resetAt: number;
}

export async function checkRateLimit(
  orgId: string,
  plan: string,
  windowSeconds = 2592000, // 30 days
): Promise<RateLimitResult> {
  const limit = PLAN_LIMITS[plan] ?? PLAN_LIMITS.STARTER;
  const key = `rl:${orgId}:compliance`;

  try {
    const redis = await getRedis();
    const now = Math.floor(Date.now() / 1000);
    const windowStart = now - (now % windowSeconds);
    const windowKey = `${key}:${windowStart}`;

    const count = await redis.incr(windowKey);
    if (count === 1) {
      await redis.expire(windowKey, windowSeconds + 60);
    }

    const remaining = Math.max(0, limit - count);
    return {
      allowed: count <= limit,
      remaining,
      limit,
      resetAt: windowStart + windowSeconds,
    };
  } catch (err) {
    console.error('[rate-limiter] Redis error, allowing request:', err);
    return { allowed: true, remaining: limit, limit, resetAt: 0 };
  }
}

export async function getRateLimitStatus(
  orgId: string,
  plan: string,
  windowSeconds = 2592000,
): Promise<RateLimitResult> {
  const limit = PLAN_LIMITS[plan] ?? PLAN_LIMITS.STARTER;
  const key = `rl:${orgId}:compliance`;

  try {
    const redis = await getRedis();
    const now = Math.floor(Date.now() / 1000);
    const windowStart = now - (now % windowSeconds);
    const windowKey = `${key}:${windowStart}`;

    const countStr = await redis.get(windowKey);
    const count = countStr ? parseInt(countStr, 10) : 0;
    const remaining = Math.max(0, limit - count);

    return {
      allowed: count < limit,
      remaining,
      limit,
      resetAt: windowStart + windowSeconds,
    };
  } catch {
    return { allowed: true, remaining: limit, limit, resetAt: 0 };
  }
}
