<template>
  <div class="admin-view-login">
    <button type="button" class="login-theme" @click="toggleTheme">
      {{ theme === 'dark' ? 'Light mode' : 'Dark mode' }}
    </button>
    <div class="login-container">
      <h1>Admin View</h1>
      <p class="sub">Sign in to manage the lottery</p>
      <form class="login-form" @submit.prevent="handleLogin">
        <div class="form-group">
          <label for="username">Username</label>
          <input
            id="username"
            v-model="username"
            type="text"
            required
            class="form-input"
            placeholder="Username"
            autocomplete="username"
          />
        </div>
        <div class="form-group">
          <label for="password">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            required
            class="form-input"
            placeholder="Password"
            autocomplete="current-password"
          />
        </div>
        <div v-if="error" class="error-message">{{ error }}</div>
        <button type="submit" class="login-btn" :disabled="loading">
          {{ loading ? 'Signing in…' : 'Login' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script>
import { secondAdminLogin } from '../services/api'
import { store, toggleTheme } from '../stores/lottery'

export default {
  name: 'SecondAdminLogin',
  data() {
    return {
      username: '',
      password: '',
      loading: false,
      error: null,
    }
  },
  computed: {
    theme() {
      return store.theme
    },
  },
  mounted() {
    document.title = 'Admin View'
  },
  methods: {
    toggleTheme,
    async handleLogin() {
      this.loading = true
      this.error = null
      try {
        await secondAdminLogin(this.username, this.password)
        this.$router.push('/admin-view')
      } catch (error) {
        this.error = error.response?.data?.error || 'Login failed. Please check your credentials.'
      } finally {
        this.loading = false
      }
    },
  },
}
</script>

<style scoped>
.admin-view-login {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(900px 420px at 50% -10%, rgb(var(--gold) / 0.10), transparent 55%),
    rgb(var(--app));
  padding: 20px;
  font-family: 'Manrope', 'Noto Sans Ethiopic', 'Segoe UI', system-ui, sans-serif;
}
.login-theme {
  position: absolute;
  top: 18px;
  right: 18px;
  border: 1px solid rgb(var(--line));
  background: rgb(var(--surface));
  color: rgb(var(--content));
  border-radius: 999px;
  padding: 0.45rem 0.75rem;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
}
.login-container {
  width: 100%;
  max-width: 400px;
  background: rgb(var(--surface));
  border: 1px solid rgb(var(--line));
  border-radius: 18px;
  padding: 1.75rem;
  box-shadow: 0 24px 70px -38px rgb(var(--shadow) / 0.4);
}
h1 {
  margin: 0;
  color: rgb(var(--gold));
  font-family: 'Fraunces', 'Noto Sans Ethiopic', Georgia, serif;
  font-size: 1.65rem;
  letter-spacing: -0.02em;
}
.sub {
  margin: 0.35rem 0 1.25rem;
  color: rgb(var(--muted));
  font-size: 0.9rem;
}
.form-group {
  margin-bottom: 1rem;
}
label {
  display: block;
  font-size: 0.85rem;
  color: rgb(var(--content) / 0.78);
  margin-bottom: 0.35rem;
}
.form-input {
  width: 100%;
  box-sizing: border-box;
  padding: 0.7rem 0.75rem;
  border-radius: 10px;
  border: 1px solid rgb(var(--line));
  background: rgb(var(--surface-2));
  color: rgb(var(--content));
}
.login-btn {
  width: 100%;
  margin-top: 0.5rem;
  border: none;
  border-radius: 10px;
  padding: 0.8rem 1rem;
  font-weight: 700;
  cursor: pointer;
  background: linear-gradient(90deg, rgb(var(--gold)), rgb(var(--gold-light)));
  color: rgb(var(--on-gold));
}
.login-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.error-message {
  background: rgb(var(--danger-bg));
  border: 1px solid rgb(var(--danger) / 0.25);
  color: rgb(var(--danger-text));
  border-radius: 10px;
  padding: 0.65rem 0.75rem;
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}
</style>
