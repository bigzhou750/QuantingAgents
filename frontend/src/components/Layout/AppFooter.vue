<template>
  <div class="app-footer">
    <span class="disclaimer">AI 分析结果仅供研究参考，不构成投资建议。市场有风险，投资需谨慎。</span>
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
