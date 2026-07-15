<template>
  <div class="admin-view-login">
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
  mounted() {
    document.title = 'Admin View'
  },
  methods: {
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
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f1115;
  padding: 20px;
  font-family: 'Segoe UI', system-ui, sans-serif;
}
.login-container {
  width: 100%;
  max-width: 400px;
  background: #161a22;
  border: 1px solid #2a3140;
  border-radius: 16px;
  padding: 1.75rem;
}
h1 {
  margin: 0;
  color: #f5a623;
  font-size: 1.5rem;
}
.sub {
  margin: 0.35rem 0 1.25rem;
  color: #9ca3af;
  font-size: 0.9rem;
}
.form-group {
  margin-bottom: 1rem;
}
label {
  display: block;
  font-size: 0.85rem;
  color: #d1d5db;
  margin-bottom: 0.35rem;
}
.form-input {
  width: 100%;
  box-sizing: border-box;
  padding: 0.7rem 0.75rem;
  border-radius: 10px;
  border: 1px solid #334155;
  background: #0d0d0d;
  color: #fff;
}
.login-btn {
  width: 100%;
  margin-top: 0.5rem;
  border: none;
  border-radius: 10px;
  padding: 0.8rem 1rem;
  font-weight: 700;
  cursor: pointer;
  background: linear-gradient(90deg, #f5a623, #ffb84d);
  color: #111;
}
.login-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.error-message {
  background: #3f1515;
  border: 1px solid #7f1d1d;
  color: #fecaca;
  border-radius: 10px;
  padding: 0.65rem 0.75rem;
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}
</style>
