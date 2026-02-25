<template>
  <pf-empty-state>
    <pf-empty-state-header title="Forbidden" heading-level="h1" />
    <pf-empty-state-body>
      You don’t have access to that area. Templates and Outputs are PM/admin-only for the currently selected org.
    </pf-empty-state-body>
    <pf-empty-state-actions>
      <pf-button variant="primary" to="/work">Go to Work</pf-button>
    </pf-empty-state-actions>
  </pf-empty-state>
</template>
