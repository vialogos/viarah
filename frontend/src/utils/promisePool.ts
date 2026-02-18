export async function mapAllSettledWithConcurrency<T, R>(
  items: readonly T[],
  concurrency: number,
  fn: (item: T) => Promise<R>
): Promise<Array<PromiseSettledResult<R>>> {
  const limit = Math.max(1, Math.floor(concurrency));
  const results: Array<PromiseSettledResult<R>> = new Array(items.length);

  let index = 0;

  async function worker() {
    while (index < items.length) {
      const currentIndex = index;
      index += 1;

      try {
        const item = items[currentIndex];
        if (item === undefined) {
          results[currentIndex] = {
            status: "rejected",
            reason: new Error(`missing item at index ${currentIndex}`),
          };
          continue;
        }

        const value = await fn(item);
        results[currentIndex] = { status: "fulfilled", value };
      } catch (reason) {
        results[currentIndex] = { status: "rejected", reason };
      }
    }
  }

  const workers = Array.from({ length: Math.min(limit, items.length) }, () => worker());
  await Promise.all(workers);
  return results;
}
