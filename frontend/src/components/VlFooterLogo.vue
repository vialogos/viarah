<template>
  <div class="vl-footer-logo">
    <a href="https://via-logos.com" target="_blank" rel="noopener" aria-label="Via Logos">
      <img src="/Via-Logos-Logo.svg" alt="Via Logos" />
    </a>
  </div>
</template>

<style scoped>
.vl-footer-logo {
  display: flex;
  justify-content: flex-end;
}

.vl-footer-logo a {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0;
}

.vl-footer-logo img {
  height: 20px;
  opacity: 0.6;
}

.vl-footer-logo a:hover img,
.vl-footer-logo a:focus-visible img {
  opacity: 0.9;
}
</style>
