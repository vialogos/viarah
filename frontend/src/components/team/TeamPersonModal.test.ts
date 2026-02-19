// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";

import TeamPersonModal from "./TeamPersonModal.vue";

async function mountWithPlugins(props: Record<string, unknown>) {
  const pinia = createPinia();
  setActivePinia(pinia);

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: { template: "<div />" } }],
  });
  await router.push("/");
  await router.isReady();

  return mount(TeamPersonModal, {
    props,
    global: {
      plugins: [pinia, router],
    },
  });
}

describe("TeamPersonModal", () => {
  it("mounts safely when open=false (no TDZ crashes)", async () => {
    const wrapper = await mountWithPlugins({ open: false });

    expect(wrapper.exists()).toBe(true);

    wrapper.unmount();
  });

  it("does not throw when toggling open -> false", async () => {
    const wrapper = await mountWithPlugins({ open: true });

    await wrapper.setProps({ open: false });

    expect(wrapper.exists()).toBe(true);

    wrapper.unmount();
  });
});
