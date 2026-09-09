<template>
  <div class="app-footer">
    <span class="disclaimer">智能投研助手 · AI 分析结果仅供研究参考，不构成投资、证券或交易建议。市场有风险，投资需谨慎。</span>
    <span class="footer-links">
      <router-link to="/pricing">定价说明</router-link>
      <router-link to="/privacy">隐私政策</router-link>
      <router-link to="/terms">服务条款</router-link>
      <a href="mailto:zh75067197@gmail.com">支持邮箱</a>
    </span>
  </div>
</template>

<script setup lang="ts">
</script>

<style lang="scss" scoped>
.app-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 16px;

  .disclaimer {
    color: var(--el-text-color-placeholder);
    font-size: 12px;
    text-align: center;
  }
}
</style>
