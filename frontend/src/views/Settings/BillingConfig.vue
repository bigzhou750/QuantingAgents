<!--
  计费配置管理页面（仅管理员可访问）。
  数据流：onMounted → loadConfig() 从后端拉取当前配置 → 用户编辑表单 → handleSave() 提交更新。
  重置操作恢复到本次页面加载时获取的值（originalForm），而非硬编码默认值，避免覆盖已有配置。
-->
<template>
  <div class="billing-config-page">
    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>算力计费配置</span>
          <el-tag type="danger" size="small">Admin Only</el-tag>
        </div>
      </template>

      <el-form
        ref="formRef"
        :model="form"
        label-width="200px"
        style="max-width: 700px"
      >
        <!--
          充值设置区块：控制用户充值行为的参数。
          每个表单项的 tooltip 采用统一结构：「作用」→「计算公式」→「具体示例」→「补充说明」，
          让管理员无需查阅文档即可理解参数的业务含义和取值影响。
        -->
        <el-divider content-position="left">充值设置</el-divider>

        <el-form-item>
          <template #label>
            充值汇率
            <el-tooltip placement="top" :show-after="200">
              <template #content>
                <div class="tooltip-content">
                  <p><strong>作用：</strong>决定用户充值后实际到账的额度。</p>
                  <p><strong>计算公式：</strong></p>
                  <code>到账额度 = 充值金额 x 充值汇率</code>
                  <p><strong>示例（汇率 = 1.2）：</strong></p>
                  <ul>
                    <li>充 100 元 → 到账 120 元额度（赠送 20 元）</li>
                    <li>充 500 元 → 到账 600 元额度（赠送 100 元）</li>
                  </ul>
                  <p>汇率 = 1.0 表示无赠送，&gt; 1.0 表示有赠送比例。</p>
                </div>
              </template>
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input-number
            v-model="form.token_exchange_rate"
            :min="0.1"
            :max="10"
            :step="0.1"
            :precision="2"
          />
        </el-form-item>

        <el-form-item>
          <template #label>
            订单过期时间
            <el-tooltip placement="top" :show-after="200">
              <template #content>
                <div class="tooltip-content">
                  <p><strong>作用：</strong>未支付订单自动标记为过期的等待时长。</p>
                  <p><strong>说明：</strong></p>
                  <ul>
                    <li>用户创建充值订单后未支付，超过此时间自动失效</li>
                    <li>后台定时任务每 2 分钟扫描一次过期订单</li>
                    <li>过期订单不会入账，用户需重新下单</li>
                  </ul>
                  <p>建议 15~30 分钟，太短用户体验差，太长占用支付通道资源。</p>
                </div>
              </template>
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input-number
            v-model="form.token_order_expire_minutes"
            :min="5"
            :max="1440"
            :step="5"
            :precision="0"
          />
          <span class="unit-label">分钟</span>
        </el-form-item>

        <!-- 消耗设置 -->
        <el-divider content-position="left">消耗设置</el-divider>

        <el-form-item>
          <template #label>
            消耗倍率
            <el-tooltip placement="top" :show-after="200">
              <template #content>
                <div class="tooltip-content">
                  <p><strong>作用：</strong>在 LLM API 原始成本基础上加收的倍率，用于覆盖运营成本和利润。</p>
                  <p><strong>计算公式：</strong></p>
                  <code>用户扣费 = API 原始成本 x 消耗倍率</code>
                  <p><strong>示例（倍率 = 1.2）：</strong></p>
                  <ul>
                    <li>API 调用花费 1.00 元 → 用户扣 1.20 元</li>
                    <li>API 调用花费 0.50 元 → 用户扣 0.60 元</li>
                  </ul>
                  <p>倍率 = 1.0 表示原价透传，&gt; 1.0 表示加价。</p>
                </div>
              </template>
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input-number
            v-model="form.token_consumption_ratio"
            :min="0.1"
            :max="10"
            :step="0.1"
            :precision="2"
          />
        </el-form-item>

        <el-form-item>
          <template #label>
            输入价格
            <el-tooltip placement="top" :show-after="200">
              <template #content>
                <div class="tooltip-content">
                  <p><strong>作用：</strong>LLM 输入 token（prompt）的单价基准。</p>
                  <p><strong>计算公式：</strong></p>
                  <code>输入成本 = (prompt_tokens / 1,000,000) x 输入价格</code>
                  <p><strong>示例（价格 = 1.0 元/百万token）：</strong></p>
                  <ul>
                    <li>1000 tokens prompt → 成本 0.001 元</li>
                    <li>10000 tokens prompt → 成本 0.01 元</li>
                  </ul>
                  <p>最终用户扣费还需乘以「消耗倍率」。</p>
                </div>
              </template>
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input-number
            v-model="form.token_input_price_per_1m"
            :min="0"
            :max="100"
            :step="0.1"
            :precision="2"
          />
          <span class="unit-label">元 / 百万 token</span>
        </el-form-item>

        <el-form-item>
          <template #label>
            输出价格
            <el-tooltip placement="top" :show-after="200">
              <template #content>
                <div class="tooltip-content">
                  <p><strong>作用：</strong>LLM 输出 token（completion）的单价基准。</p>
                  <p><strong>计算公式：</strong></p>
                  <code>输出成本 = (completion_tokens / 1,000,000) x 输出价格</code>
                  <p><strong>示例（价格 = 2.0 元/百万token）：</strong></p>
                  <ul>
                    <li>500 tokens 回复 → 成本 0.001 元</li>
                    <li>5000 tokens 回复 → 成本 0.01 元</li>
                  </ul>
                  <p>通常输出价格高于输入价格。最终扣费 = (输入成本 + 输出成本) x 消耗倍率。</p>
                </div>
              </template>
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input-number
            v-model="form.token_output_price_per_1m"
            :min="0"
            :max="100"
            :step="0.1"
            :precision="2"
          />
          <span class="unit-label">元 / 百万 token</span>
        </el-form-item>

        <!--
          完整计算示例区块：将上方所有消耗参数串联为一个端到端的扣费演算，
          帮助管理员直观验证「输入价格 + 输出价格 + 消耗倍率」组合后的实际用户扣费效果。
        -->
        <div class="calc-example">
          <el-icon><InfoFilled /></el-icon>
          <div>
            <strong>单次对话扣费完整示例</strong>
            <p>
              假设 prompt 2000 tokens、completion 800 tokens，输入价格 1.0、输出价格 2.0、消耗倍率 1.2：
            </p>
            <code>
              输入成本 = 2000 / 1,000,000 x 1.0 = 0.002 元<br/>
              输出成本 = 800 / 1,000,000 x 2.0 = 0.0016 元<br/>
              API 总成本 = 0.002 + 0.0016 = 0.0036 元<br/>
              用户扣费 = 0.0036 x 1.2 = <strong>0.00432 元</strong>
            </code>
          </div>
        </div>

        <!-- 风控设置 -->
        <el-divider content-position="left">风控设置</el-divider>

        <el-form-item>
          <template #label>
            预占倍率
            <el-tooltip placement="top" :show-after="200">
              <template #content>
                <div class="tooltip-content">
                  <p><strong>作用：</strong>Agent 任务开始时预冻结的额度倍率，防止余额不足时任务中途失败。</p>
                  <p><strong>计算公式：</strong></p>
                  <code>预冻结额度 = 预估首轮消耗 x 预占倍率</code>
                  <p><strong>机制说明：</strong></p>
                  <ul>
                    <li>采用「轻预占 + 实时追扣」策略</li>
                    <li>首轮仅预占少量额度（约 12mq ≈ 0.012 元）</li>
                    <li>后续每轮 LLM 调用按实际用量实时扣减</li>
                    <li>任务结束时释放剩余冻结额度</li>
                  </ul>
                  <p>倍率越高安全余量越大，但会暂时占用更多可用余额。</p>
                </div>
              </template>
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input-number
            v-model="form.token_preoccupy_ratio"
            :min="1.0"
            :max="5.0"
            :step="0.1"
            :precision="2"
          />
        </el-form-item>

        <el-form-item>
          <template #label>
            低余额预警阈值
            <el-tooltip placement="top" :show-after="200">
              <template #content>
                <div class="tooltip-content">
                  <p><strong>作用：</strong>当用户余额低于此值时，前端显示黄色警告提示。</p>
                  <p><strong>表现：</strong></p>
                  <ul>
                    <li>Agent 对话页顶部余额芯片变为黄色</li>
                    <li>提示用户及时充值</li>
                    <li>余额归零时禁止发送消息并引导充值</li>
                  </ul>
                  <p>设为 0 可关闭预警。</p>
                </div>
              </template>
              <el-icon class="help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input-number
            v-model="form.token_balance_warn_threshold"
            :min="0"
            :max="1000"
            :step="1"
            :precision="2"
          />
          <span class="unit-label">元</span>
        </el-form-item>

        <!-- 操作按钮 -->
        <el-divider />

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="handleSave">
            保存配置
          </el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<!--
  表单数据流：
  1. loadConfig() 从后端 GET 接口拉取当前配置，填充 form；同时将快照存入 originalForm。
  2. 用户在表单中修改值（v-model 双向绑定）。
  3. handleSave() 将 form 整体 PUT 到后端；成功后刷新 originalForm 为最新值。
  4. handleReset() 将 form 回退到 originalForm（即上次加载/保存时的状态），而非 defaultForm。
  defaultForm 仅在后端返回字段缺失时作为兜底默认值使用。
-->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled, InfoFilled } from '@element-plus/icons-vue'
import { tokenBillingApi } from '@/api/tokenBilling'

const loading = ref(false)
const saving = ref(false)

interface BillingForm {
  token_exchange_rate: number
  token_consumption_ratio: number
  token_input_price_per_1m: number
  token_output_price_per_1m: number
  token_preoccupy_ratio: number
  token_balance_warn_threshold: number
  token_order_expire_minutes: number
}

const defaultForm: BillingForm = {
  token_exchange_rate: 1.1,
  token_consumption_ratio: 1.2,
  token_input_price_per_1m: 1.0,
  token_output_price_per_1m: 2.0,
  token_preoccupy_ratio: 1.2,
  token_balance_warn_threshold: 5.0,
  token_order_expire_minutes: 30,
}

const form = ref<BillingForm>({ ...defaultForm })
// 保存「上次从服务端获取或成功保存后的快照」，重置时回退到此值而非 defaultForm
const originalForm = ref<BillingForm>({ ...defaultForm })

async function loadConfig() {
  loading.value = true
  try {
    const res = await tokenBillingApi.getBillingConfig()
    if (res.success && res.data) {
      const config = res.data as Record<string, any>
      // 后端返回的字段带 token_ 前缀，直接映射
      form.value = {
        token_exchange_rate: config.token_exchange_rate ?? defaultForm.token_exchange_rate,
        token_consumption_ratio: config.token_consumption_ratio ?? defaultForm.token_consumption_ratio,
        token_input_price_per_1m: config.token_input_price_per_1m ?? defaultForm.token_input_price_per_1m,
        token_output_price_per_1m: config.token_output_price_per_1m ?? defaultForm.token_output_price_per_1m,
        token_preoccupy_ratio: config.token_preoccupy_ratio ?? defaultForm.token_preoccupy_ratio,
        token_balance_warn_threshold: config.token_balance_warn_threshold ?? defaultForm.token_balance_warn_threshold,
        token_order_expire_minutes: config.token_order_expire_minutes ?? defaultForm.token_order_expire_minutes,
      }
      originalForm.value = { ...form.value }
    }
  } catch (e: any) {
    ElMessage.error('加载计费配置失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    const res = await tokenBillingApi.updateBillingConfig(form.value)
    if (res.success) {
      ElMessage.success('计费配置已保存')
      originalForm.value = { ...form.value }
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e: any) {
    ElMessage.error('保存失败: ' + (e.message || e))
  } finally {
    saving.value = false
  }
}

function handleReset() {
  form.value = { ...originalForm.value }
  ElMessage.info('已重置为上次保存的值')
}

onMounted(() => {
  loadConfig()
})
</script>

<style lang="scss" scoped>
.billing-config-page {
  max-width: 900px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 16px;
  font-weight: 600;
}

.help-icon {
  margin-left: 4px;
  color: var(--el-text-color-secondary);
  cursor: help;
  font-size: 14px;
  vertical-align: middle;
}

.unit-label {
  margin-left: 8px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.calc-example {
  display: flex;
  gap: 10px;
  padding: 14px 18px;
  margin: 8px 0 16px 0;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--el-text-color-regular);

  .el-icon {
    margin-top: 3px;
    color: var(--el-color-primary);
    flex-shrink: 0;
  }

  code {
    display: block;
    margin-top: 6px;
    font-family: 'SF Mono', Monaco, Consolas, monospace;
    font-size: 12px;
    color: var(--el-text-color-primary);
  }

  p {
    margin: 4px 0 0 0;
  }
}

.tooltip-content {
  max-width: 380px;
  line-height: 1.6;

  p {
    margin: 6px 0;
  }

  ul {
    margin: 4px 0;
    padding-left: 18px;
  }

  li {
    margin: 2px 0;
  }

  code {
    display: block;
    margin: 6px 0;
    padding: 6px 10px;
    background: rgba(255, 255, 255, 0.15);
    border-radius: 4px;
    font-family: 'SF Mono', Monaco, Consolas, monospace;
    font-size: 12px;
  }
}
</style>
