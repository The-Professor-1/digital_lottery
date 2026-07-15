<template>
  <!-- Kept for backward imports; route now uses AdminDashboard variant=view -->
  <AdminDashboard variant="view" />
</template>

<script>
import AdminDashboard from './AdminDashboard.vue'

export default {
  name: 'SecondAdminDashboard',
  components: { AdminDashboard },
}
</script>
