<template>
  <div class="investment-profile">
    <!-- 首次使用引导 -->
    <el-alert
      v-if="isFirstTime"
      type="info"
      :closable="false"
      show-icon
      class="onboarding-alert"
    >
      <template #title>
        <div class="onboarding-content">
          <strong>欢迎使用个人投资助手</strong>
          <p>先选择一个贴近你风险偏好的起步模板，系统会帮你预填常用参数，之后你可以随时调整。这不是投资建议，只是帮你更快完成第一次设置。</p>
        </div>
      </template>
    </el-alert>

    <!-- 画像模板选择 -->
    <el-card class="template-card" v-if="isFirstTime || showTemplates">
      <template #header>
        <div class="card-header">
          <span>选择起步模板</span>
          <el-button v-if="!isFirstTime" link @click="showTemplates = false">收起</el-button>
        </div>
      </template>
      <div class="template-list">
        <div
          v-for="tpl in profileTemplates"
          :key="tpl.key"
          class="template-item"
          :class="{ active: selectedTemplate === tpl.key }"
          @click="applyTemplate(tpl.key)"
        >
          <div class="template-icon" :style="{ color: tpl.color }">
            <el-icon :size="28"><component :is="tpl.icon" /></el-icon>
          </div>
          <div class="template-name">{{ tpl.label }}</div>
          <div class="template-desc">{{ tpl.description }}</div>
        </div>
      </div>
      <div class="template-tip">
        模板只是预填表单，不代表推荐结论，你可以在下方随时修改任何字段。
      </div>
    </el-card>

    <el-card class="profile-card">
      <template #header>
        <div class="card-header">
          <span>投资画像设置</span>
          <div class="header-actions">
            <el-button v-if="!isFirstTime && !showTemplates" link @click="showTemplates = true">
              重新选择模板
            </el-button>
            <el-switch
              v-model="contextInjectionEnabled"
              active-text="启用上下文注入"
              inactive-text="关闭"
              @change="(val: any) => toggleContextInjection(val)"
            />
          </div>
        </div>
      </template>

      <el-form
        ref="formRef"
        :model="profileForm"
        :rules="rules"
        label-width="120px"
        class="profile-form"
      >
        <!-- 风险偏好 -->
        <el-form-item label="风险偏好" prop="risk_preference">
          <el-radio-group v-model="profileForm.risk_preference">
            <el-radio value="conservative">保守型</el-radio>
            <el-radio value="balanced">平衡型</el-radio>
            <el-radio value="aggressive">进取型</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 交易风格 -->
        <el-form-item label="交易风格" prop="trading_style">
          <el-select v-model="profileForm.trading_style" placeholder="请选择">
            <el-option label="价值投资" value="value" />
            <el-option label="成长投资" value="growth" />
            <el-option label="趋势跟踪" value="momentum" />
            <el-option label="红利投资" value="dividend" />
            <el-option label="逆向投资" value="contrarian" />
          </el-select>
        </el-form-item>

        <!-- 资金范围 -->
        <el-form-item label="资金范围" prop="capital_range">
          <div class="capital-range">
            <el-input-number
              v-model="profileForm.capital_range_min"
              :min="0"
              :step="10000"
              placeholder="最小"
            />
            <span class="separator">-</span>
            <el-input-number
              v-model="profileForm.capital_range_max"
              :min="0"
              :step="10000"
              placeholder="最大"
            />
            <span class="unit">元</span>
          </div>
        </el-form-item>

        <!-- 目标市场 -->
        <el-form-item label="目标市场" prop="target_markets">
          <el-checkbox-group v-model="profileForm.target_markets">
            <el-checkbox value="A股">A股</el-checkbox>
            <el-checkbox value="港股">港股</el-checkbox>
            <el-checkbox value="美股">美股</el-checkbox>
            <el-checkbox value="基金">基金</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <!-- 排除规则 -->
        <el-divider content-position="left">排除规则</el-divider>

        <el-form-item label="排除 ST 股票">
          <el-switch v-model="profileForm.exclude_st" />
        </el-form-item>

        <el-form-item label="回避行业">
          <el-select
            v-model="profileForm.excluded_sectors"
            multiple
            filterable
            allow-create
            placeholder="输入行业名称后回车添加"
          >
            <el-option label="房地产" value="房地产" />
            <el-option label="金融" value="金融" />
            <el-option label="医药" value="医药" />
            <el-option label="科技" value="科技" />
          </el-select>
        </el-form-item>

        <el-form-item label="回避标的">
          <el-select
            v-model="profileForm.excluded_stocks"
            multiple
            filterable
            allow-create
            placeholder="输入股票代码或名称"
          />
        </el-form-item>

        <!-- 仓位约束 -->
        <el-divider content-position="left">仓位约束</el-divider>

        <el-form-item label="单只最大仓位">
          <el-slider
            v-model="maxPositionPercent"
            :min="5"
            :max="100"
            :step="5"
            show-input
            @change="(val: any) => updateMaxPosition(val)"
          />
          <div class="form-tip">建议不超过 20%，以分散风险</div>
        </el-form-item>

        <!-- 当前持仓 -->
        <el-form-item label="当前持仓">
          <el-button type="primary" plain @click="showHoldingsDialog = true">
            管理持仓 ({{ profileForm.current_holdings?.length || 0 }} 只)
          </el-button>
        </el-form-item>

        <!-- 操作按钮 -->
        <el-form-item>
          <el-button type="primary" @click="saveProfile" :loading="saving">
            保存画像
          </el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 持仓管理对话框 -->
    <el-dialog v-model="showHoldingsDialog" title="管理当前持仓" width="600px">
        <el-table :data="profileForm.current_holdings" border>
          <el-table-column prop="stock_code" label="代码" width="100" />
          <el-table-column prop="stock_name" label="名称" width="120" />
          <el-table-column prop="quantity" label="数量" width="100" />
          <el-table-column prop="cost_price" label="成本价" width="100" />
        <el-table-column label="操作" width="80">
          <template #default="{ $index }">
            <el-button type="danger" size="small" link @click="removeHolding($index)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 16px;">
        <el-button type="primary" @click="openHoldingDialog">添加持仓</el-button>
      </div>
    </el-dialog>

    <el-dialog v-model="showHoldingEditor" title="添加持仓" width="520px">
      <el-form :model="holdingDraft" label-width="90px">
        <el-form-item label="代码">
          <el-input v-model="holdingDraft.stock_code" placeholder="如 600519" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="holdingDraft.stock_name" placeholder="如 贵州茅台" />
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="holdingDraft.quantity" :min="0" :step="100" />
        </el-form-item>
        <el-form-item label="成本价">
          <el-input-number v-model="holdingDraft.cost_price" :min="0" :step="0.1" :precision="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showHoldingEditor = false">取消</el-button>
        <el-button type="primary" @click="confirmHolding">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Umbrella, Coin, TrendCharts } from '@element-plus/icons-vue'
import { investmentApi } from '@/api/investment'

const formRef = ref<FormInstance>()
const saving = ref(false)
const contextInjectionEnabled = ref(true)
const showHoldingsDialog = ref(false)
const showHoldingEditor = ref(false)
const isFirstTime = ref(false)
const showTemplates = ref(false)
const selectedTemplate = ref('')
const holdingDraft = reactive({
  stock_code: '',
  stock_name: '',
  quantity: 0,
  cost_price: 0,
})

// 起步模板：仅用于预填表单，不构成投资建议
const profileTemplates = [
  {
    key: 'conservative',
    label: '保守型',
    description: '优先控制波动，偏好低估值、分红稳定的标的',
    icon: Umbrella,
    color: '#67C23A',
    values: {
      risk_preference: 'conservative',
      trading_style: 'dividend',
      target_markets: ['A股'],
      exclude_st: true,
      max_position_per_stock: 0.15,
    },
  },
  {
    key: 'balanced',
    label: '平衡型',
    description: '兼顾成长与稳健，适合大多数新手起步',
    icon: Coin,
    color: '#409EFF',
    values: {
      risk_preference: 'balanced',
      trading_style: 'value',
      target_markets: ['A股'],
      exclude_st: true,
      max_position_per_stock: 0.2,
    },
  },
  {
    key: 'aggressive',
    label: '进取型',
    description: '愿意承担更高波动以追求成长机会',
    icon: TrendCharts,
    color: '#E6A23C',
    values: {
      risk_preference: 'aggressive',
      trading_style: 'growth',
      target_markets: ['A股'],
      exclude_st: false,
      max_position_per_stock: 0.25,
    },
  },
]

// 应用模板：仅预填表单字段，用户可继续编辑
const applyTemplate = (key: string) => {
  const tpl = profileTemplates.find(t => t.key === key)
  if (!tpl) return
  selectedTemplate.value = key
  Object.assign(profileForm, tpl.values)
  ElMessage.success(`已套用「${tpl.label}」模板，可继续调整下方字段`)
  if (isFirstTime.value) {
    isFirstTime.value = false
  }
  showTemplates.value = false
}

// 表单数据
const profileForm = reactive({
  risk_preference: 'balanced',
  trading_style: 'value',
  capital_range_min: 10000,
  capital_range_max: 500000,
  target_markets: ['A股'],
  excluded_sectors: [] as string[],
  excluded_stocks: [] as string[],
  exclude_st: true,
  exclude_new_stock_days: 60,
  max_position_per_stock: 0.2,
  current_holdings: [] as any[],
  context_injection_enabled: true,
})

// 计算属性用于滑块显示
const maxPositionPercent = computed({
  get: () => Math.round(profileForm.max_position_per_stock * 100),
  set: (val: number) => {
    profileForm.max_position_per_stock = val / 100
  },
})

// 表单验证规则
const rules: FormRules = {
  risk_preference: [{ required: true, message: '请选择风险偏好', trigger: 'change' }],
  trading_style: [{ required: true, message: '请选择交易风格', trigger: 'change' }],
}

// 加载画像数据
const loadProfile = async () => {
  try {
    const response = await investmentApi.getProfile()
    if (response.success && response.data && Object.keys(response.data).length > 0) {
      Object.assign(profileForm, response.data)
      contextInjectionEnabled.value = profileForm.context_injection_enabled ?? true
      isFirstTime.value = false
    } else {
      isFirstTime.value = true
    }
  } catch (error: any) {
    if (error.response?.status === 404) {
      isFirstTime.value = true
    } else {
      ElMessage.error('加载画像失败')
    }
  }
}

// 保存画像
const saveProfile = async () => {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (!valid) return

    saving.value = true
    try {
      const response = await investmentApi.updateProfile({
        ...profileForm,
        context_injection_enabled: contextInjectionEnabled.value,
      })

      if (response.success) {
        ElMessage.success('画像保存成功')
        isFirstTime.value = false
      } else {
        ElMessage.error(response.message || '保存失败')
      }
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '保存失败')
    } finally {
      saving.value = false
    }
  })
}

// 重置表单
const resetForm = () => {
  formRef.value?.resetFields()
  loadProfile()
}

// 切换上下文注入
const toggleContextInjection = (val: boolean) => {
  profileForm.context_injection_enabled = val
}

// 更新最大仓位
const updateMaxPosition = (val: number) => {
  profileForm.max_position_per_stock = val / 100
}

// 移除持仓
const removeHolding = (index: number) => {
  profileForm.current_holdings.splice(index, 1)
}

// 添加持仓（简化版，实际应该弹出表单）
const openHoldingDialog = () => {
  holdingDraft.stock_code = ''
  holdingDraft.stock_name = ''
  holdingDraft.quantity = 0
  holdingDraft.cost_price = 0
  showHoldingEditor.value = true
}

const confirmHolding = () => {
  if (!holdingDraft.stock_code || !holdingDraft.stock_name) {
    ElMessage.warning('请输入持仓代码和名称')
    return
  }
  profileForm.current_holdings.push({
    stock_code: holdingDraft.stock_code,
    stock_name: holdingDraft.stock_name,
    quantity: holdingDraft.quantity,
    cost_price: holdingDraft.cost_price,
  })
  showHoldingEditor.value = false
  ElMessage.success('已添加到当前持仓，保存画像后生效')
}

onMounted(() => {
  loadProfile()
})
</script>

<style scoped>
.investment-profile {
  padding: 20px;
}

.onboarding-alert {
  max-width: 800px;
  margin: 0 auto 16px;
}

.onboarding-content p {
  margin: 8px 0 0 0;
  color: #606266;
  font-size: 13px;
}

.template-card {
  max-width: 800px;
  margin: 0 auto 16px;
}

.template-list {
  display: flex;
  gap: 16px;
}

.template-item {
  flex: 1;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 20px 12px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.template-item:hover {
  border-color: #409EFF;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.template-item.active {
  border-color: #409EFF;
  background-color: #ecf5ff;
}

.template-icon {
  margin-bottom: 8px;
}

.template-name {
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}

.template-desc {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.template-tip {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
  text-align: center;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.profile-card {
  max-width: 800px;
  margin: 0 auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.profile-form {
  margin-top: 20px;
}

.capital-range {
  display: flex;
  align-items: center;
  gap: 8px;
}

.separator {
  color: #909399;
}

.unit {
  color: #606266;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
