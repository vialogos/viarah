import { createRouter, createWebHistory } from "vue-router";

import { useSessionStore } from "./stores/session";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("./pages/LoginPage.vue"),
      meta: { public: true },
    },
    {
      path: "/",
      component: () => import("./layouts/AppShell.vue"),
      children: [
        { path: "", redirect: "/work" },
        { path: "work", name: "work-list", component: () => import("./pages/WorkListPage.vue") },
        {
          path: "work/:taskId",
          name: "work-detail",
          component: () => import("./pages/WorkDetailPage.vue"),
          props: true,
        },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  const session = useSessionStore();
  if (!session.initialized) {
    await session.bootstrap();
  }

  if (to.meta.public) {
    if (session.user && to.path === "/login") {
      return { path: "/work" };
    }
    return true;
  }

  if (!session.user) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }

  return true;
});

export default router;
