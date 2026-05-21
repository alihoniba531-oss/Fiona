// Kill-switch service worker.
// 现阶段菲欧娜在 dev 模式下迭代非常频繁，cache-first 的 SW 反复让浏览器
// serve 老 chunk → 用户看到的 UI 和最新代码不一致。
// 这版 SW 上线后会主动自杀：装上就 unregister 自己 + 清掉所有缓存 + 强制刷
// 客户端。等以后真要做 PWA 离线能力时再换回真正的缓存策略。

self.addEventListener("install", () => {
  self.skipWaiting(); // 不等旧 SW 关闭，立刻 activate
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // 1. 清掉所有 cache
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));

      // 2. 卸载自己
      await self.registration.unregister();

      // 3. 通知所有正在跑的 tab 重新 navigate（拿到没 SW 拦截的真版资源）
      const clients = await self.clients.matchAll({ type: "window" });
      clients.forEach((c) => c.navigate(c.url));
    })()
  );
});

// 不注册 fetch handler —— 任何 fetch 都走真实网络
