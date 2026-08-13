import { mount } from "svelte";
import App from "./App.svelte";
import { registerServiceWorker } from "./sw-register";
import "./app.css";
import "./designsystem/animations.css";

const target = document.getElementById("app");
if (!target) {
  throw new Error("yen-tamizh: root element #app not found");
}

const app = mount(App, { target });

registerServiceWorker();

export default app;
