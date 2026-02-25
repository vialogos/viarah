import { createPinia } from "pinia";
import { createApp } from "vue";
import VuePatternFly from "@vue-patternfly/core";
import VuePatternFlyTable from "@vue-patternfly/table";

import App from "./App.vue";
import router from "./router";
import "@patternfly/patternfly/patternfly.css";
import "@patternfly/patternfly/patternfly-addons.css";
import "./style.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.use(VuePatternFly);
app.use(VuePatternFlyTable);
app.mount("#app");
