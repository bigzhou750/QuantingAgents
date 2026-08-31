<template>
  <div class="strategy-management">
    <!-- 策略怎么选向导入口 -->
    <el-card class="guide-entry-card" shadow="never">
      <div class="guide-entry">
        <div class="guide-entry-text">
          <strong>不确定该从哪类策略开始？</strong>
          <span>先回答几个问题，了解适合你的策略类型、适用场景和证据层级</span>
        </div>
        <el-button type="primary" plain @click="showGuideDialog = true">策略怎么选</el-button>
      </div>
    </el-card>

    <!-- 默认策略模板 -->
    <el-card class="template-strategy-card" v-if="strategies.length === 0 && !loading">
      <template #header>
        <span>从模板开始（推荐新手）</span>
      </template>
      <div class="strategy-template-list">
        <div
          v-for="tpl in strategyTemplates"
          :key="tpl.key"
          class="strategy-template-item"
          @click="createFromTemplate(tpl)"
        >
          <div class="strategy-template-name">{{ tpl.name }}</div>
          <div class="strategy-template-desc">{{ tpl.description }}</div>
          <el-tag
            v-for="tag in tpl.tags"
            :key="tag"
            size="small"
            style="margin-right: 4px; margin-top: 8px;"
          >
            {{ tag }}
          </el-tag>
        </div>
      </div>
      <div class="strategy-template-tip">
        模板会创建一份可编辑的策略草稿，条件仅作为筛选起点，不构成投资建议。
      </div>
    </el-card>

    <el-card>
      <template #header>
        <div class="card-header">
          <span>策略管理</span>
          <el-button type="primary" @click="showCreateDialog = true">
            <el-icon><Plus /></el-icon>
            创建策略
          </el-button>
        </div>
      </template>

      <!-- 策略列表 -->
      <el-table :data="strategies" v-loading="loading" border stripe>
        <el-table-column prop="name" label="策略名称" min-width="150" />
        <el-table-column prop="description" label="说明" min-width="200" show-overflow-tooltip />
        <el-table-column label="适用市场" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.applicable_markets?.join(', ') || 'A股' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标签" width="200">
          <template #default="{ row }">
            <el-tag
              v-for="tag in row.tags"
              :key="tag"
              size="small"
              style="margin-right: 4px;"
            >
              {{ tagLabel(tag) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="editStrategy(row)">编辑</el-button>
            <el-button
              size="small"
              :type="row.status === 'active' ? 'warning' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? '停用' : '启用' }}
            </el-button>
            <el-dropdown trigger="click" @command="(cmd: string) => openTaskWizard(cmd, row)">
              <el-button size="small" type="primary">
                执行<el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="screening">策略选股</el-dropdown-item>
                  <el-dropdown-item command="checkup">策略体检（含证据验证）</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑策略对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingStrategy ? '编辑策略' : '创建策略'"
      width="700px"
    >
      <el-form
        ref="strategyFormRef"
        :model="strategyForm"
        :rules="strategyRules"
        label-width="100px"
      >
        <el-form-item label="策略名称" prop="name">
          <el-input v-model="strategyForm.name" placeholder="例如：价值投资策略" />
        </el-form-item>

        <el-form-item label="策略说明" prop="description">
          <el-input
            v-model="strategyForm.description"
            type="textarea"
            :rows="3"
            placeholder="描述您的策略逻辑和目标"
          />
        </el-form-item>

        <el-form-item label="适用市场">
          <el-checkbox-group v-model="strategyForm.applicable_markets">
            <el-checkbox value="A股">A股</el-checkbox>
            <el-checkbox value="港股">港股</el-checkbox>
            <el-checkbox value="美股">美股</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="标签">
          <el-select
            v-model="strategyForm.tags"
            multiple
            filterable
            allow-create
            placeholder="输入标签后回车添加"
          >
            <el-option label="价值" value="value" />
            <el-option label="成长" value="growth" />
            <el-option label="红利" value="dividend" />
            <el-option label="趋势" value="momentum" />
            <el-option label="稳健" value="conservative" />
          </el-select>
        </el-form-item>

        <el-divider content-position="left">筛选条件</el-divider>

        <el-form-item label="PE 上限">
          <el-input-number v-model="strategyForm.screening_criteria.pe_max" :min="0" :max="200" />
        </el-form-item>

        <el-form-item label="ROE 下限 (%)">
          <el-input-number v-model="strategyForm.screening_criteria.roe_min" :min="0" :max="100" />
        </el-form-item>

        <el-form-item label="RSI 范围">
          <div class="range-input">
            <el-input-number
              v-model="strategyForm.screening_criteria.rsi_min"
              :min="0"
              :max="100"
              placeholder="最小"
            />
            <span>-</span>
            <el-input-number
              v-model="strategyForm.screening_criteria.rsi_max"
              :min="0"
              :max="100"
              placeholder="最大"
            />
          </div>
        </el-form-item>

        <el-form-item label="MA 趋势">
          <el-select v-model="strategyForm.screening_criteria.ma_trend" clearable>
            <el-option label="上升趋势 (价格 > MA20)" value="up" />
            <el-option label="下降趋势 (价格 < MA20)" value="down" />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="saveStrategy" :loading="saving">
          {{ editingStrategy ? '更新' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 策略怎么选向导 -->
    <el-dialog v-model="showGuideDialog" title="策略怎么选" width="600px">
      <div v-if="guideStep === 1" class="guide-step">
        <p class="guide-question">你更看重哪种投资体验？</p>
        <el-radio-group v-model="guideAnswers.risk" class="guide-options">
          <el-radio value="conservative">控制波动，追求稳健（保守型）</el-radio>
          <el-radio value="balanced">兼顾成长与稳健（平衡型）</el-radio>
          <el-radio value="aggressive">能承受较大波动追求成长（进取型）</el-radio>
        </el-radio-group>
      </div>
      <div v-else-if="guideStep === 2" class="guide-step">
        <p class="guide-question">你更认同哪种选股逻辑？</p>
        <el-radio-group v-model="guideAnswers.style" class="guide-options">
          <el-radio value="value">低估值、财务稳健（价值投资）</el-radio>
          <el-radio value="growth">业绩持续增长（成长投资）</el-radio>
          <el-radio value="dividend">稳定分红（红利投资）</el-radio>
          <el-radio value="momentum">跟随价格趋势（趋势跟踪）</el-radio>
        </el-radio-group>
      </div>
      <div v-else class="guide-result">
        <el-result icon="success" :title="guideRecommendation?.name || ''">
          <template #sub-title>
            <div class="guide-result-body">
              <p>{{ guideRecommendation?.description }}</p>
              <div class="guide-evidence">
                <div class="guide-evidence-row">
                  <strong>适用人群：</strong>{{ guideRecommendation?.audience }}
                </div>
                <div class="guide-evidence-row">
                  <strong>适用市场环境：</strong>{{ guideRecommendation?.marketCondition }}
                </div>
                <div class="guide-evidence-row">
                  <strong>证据层级：</strong>{{ guideRecommendation?.evidenceLevel }}
                </div>
                <div class="guide-evidence-row">
                  <strong>失效条件：</strong>{{ guideRecommendation?.invalidation }}
                </div>
              </div>
              <el-alert type="info" :closable="false" show-icon style="margin-top: 12px;">
                这是策略类型匹配建议，不是股票推荐，也不保证收益。你仍需要结合策略体检和历史证据自行判断。
              </el-alert>
            </div>
          </template>
        </el-result>
      </div>
      <template #footer>
        <el-button v-if="guideStep > 1 && guideStep <= 2" @click="guideStep--">上一步</el-button>
        <el-button v-if="guideStep < 2" type="primary" @click="guideStep++">下一步</el-button>
        <el-button v-if="guideStep === 2" type="primary" @click="guideStep = 3">查看建议</el-button>
        <el-button v-if="guideStep === 3" type="primary" @click="applyGuideResult">按此创建策略</el-button>
        <el-button v-if="guideStep === 3" @click="resetGuide">重新回答</el-button>
      </template>
    </el-dialog>

    <!-- 任务确认向导：策略选股 / 策略体检 -->
    <el-dialog v-model="showTaskWizard" :title="taskWizardTitle" width="560px">
      <div class="task-wizard">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="策略">{{ taskWizardStrategy?.name }}</el-descriptions-item>
          <el-descriptions-item label="任务类型">
            {{ taskWizardType === 'screening' ? '策略选股' : '策略体检' }}
          </el-descriptions-item>
          <el-descriptions-item label="适用市场">
            {{ taskWizardStrategy?.applicable_markets?.join('、') || 'A股' }}
          </el-descriptions-item>
          <el-descriptions-item v-if="taskWizardType === 'screening'" label="筛选条件">
            <div v-if="hasScreeningCriteria">
              <el-tag v-if="taskWizardStrategy?.screening_criteria?.pe_max" size="small" style="margin: 2px;">
                PE ≤ {{ taskWizardStrategy.screening_criteria.pe_max }}
              </el-tag>
              <el-tag v-if="taskWizardStrategy?.screening_criteria?.roe_min" size="small" style="margin: 2px;">
                ROE ≥ {{ taskWizardStrategy.screening_criteria.roe_min }}%
              </el-tag>
              <el-tag v-if="taskWizardStrategy?.screening_criteria?.ma_trend" size="small" style="margin: 2px;">
                {{ taskWizardStrategy.screening_criteria.ma_trend === 'up' ? '上升趋势' : '下降趋势' }}
              </el-tag>
            </div>
            <span v-else class="wizard-muted">未设置额外筛选条件</span>
          </el-descriptions-item>
        </el-descriptions>

        <el-form label-width="140px" style="margin-top: 16px;">
          <el-form-item label="带入投资画像">
            <el-switch v-model="taskWizardUseProfile" :disabled="!currentProfileId" />
            <div class="form-tip">
              <template v-if="currentProfileId">开启后将结合你的风险偏好和排除规则进行匹配，不代表最终推荐</template>
              <template v-else>
                你还没有设置投资画像，
                <el-button link type="primary" size="small" @click="$router.push('/investment/profile')">去设置</el-button>
              </template>
            </div>
          </el-form-item>
        </el-form>

        <el-alert
          v-if="taskWizardType === 'screening'"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 12px;"
        >
          <template #title>
            选股结果是基于规则匹配的候选研究方向，不构成买入或卖出建议，请结合体检和自行研究再做判断。
          </template>
        </el-alert>
        <el-alert
          v-else
          type="info"
          :closable="false"
          show-icon
          style="margin-top: 12px;"
        >
          <template #title>
            策略体检基于历史数据和规则匹配评估适配度，不是回测，也不构成收益承诺。数据不足时会明确提示。
          </template>
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="showTaskWizard = false">取消</el-button>
        <el-button type="primary" @click="confirmTaskWizard" :loading="creatingTask">
          确认发起
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, ArrowDown } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { investmentApi } from '@/api/investment'
import { getStrategyGuideRecommendation } from '@/utils/strategyGuide'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const strategies = ref<any[]>([])
const showCreateDialog = ref(false)
const editingStrategy = ref<any>(null)
const strategyFormRef = ref<FormInstance>()

// 默认策略模板：用于新手从空白开始创建策略草稿
const strategyTemplates = [
  {
    key: 'value_dividend',
    name: '低估值红利策略',
    description: '筛选低 PE、稳定分红的标的，适合追求稳健的新手',
    tags: ['价值', '红利', '稳健'],
    values: {
      description: '筛选低估值、分红稳定的标的，控制波动为主要目标',
      applicable_markets: ['A股'],
      tags: ['value', 'dividend', 'conservative'],
      screening_criteria: { pe_max: 20, roe_min: 8, rsi_min: undefined, rsi_max: undefined, ma_trend: undefined },
    },
  },
  {
    key: 'growth_momentum',
    name: '成长趋势策略',
    description: '关注业绩增长且价格处于上升趋势的标的',
    tags: ['成长', '趋势'],
    values: {
      description: '关注 ROE 较高且股价处于上升趋势的成长型标的',
      applicable_markets: ['A股'],
      tags: ['growth', 'momentum'],
      screening_criteria: { pe_max: 60, roe_min: 12, rsi_min: 40, rsi_max: 70, ma_trend: 'up' },
    },
  },
  {
    key: 'balanced_start',
    name: '均衡起步策略',
    description: '不设过多限制，适合先跑通一次完整流程再调整',
    tags: ['均衡', '新手'],
    values: {
      description: '较宽松的筛选条件，用于熟悉选股和体检流程',
      applicable_markets: ['A股'],
      tags: ['balanced'],
      screening_criteria: { pe_max: 40, roe_min: 5, rsi_min: undefined, rsi_max: undefined, ma_trend: undefined },
    },
  },
]

const createFromTemplate = (tpl: typeof strategyTemplates[number]) => {
  editingStrategy.value = null
  Object.assign(strategyForm, {
    name: tpl.name,
    ...tpl.values,
  })
  showCreateDialog.value = true
}

const strategyTagLabels: Record<string, string> = {
  balanced: '均衡',
  value: '价值',
  growth: '成长',
  dividend: '红利',
  momentum: '趋势',
  conservative: '稳健',
}

const tagLabel = (tag: string) => strategyTagLabels[tag] || tag

// 策略怎么选向导
const showGuideDialog = ref(false)
const guideStep = ref(1)
const guideAnswers = reactive({
  risk: '',
  style: '',
})

const guideRecommendation = computed(() => getStrategyGuideRecommendation(guideAnswers.risk, guideAnswers.style))

const applyGuideResult = () => {
  const rec = guideRecommendation.value
  editingStrategy.value = null
  Object.assign(strategyForm, {
    name: rec.name,
    description: rec.description,
    applicable_markets: ['A股'],
    tags: [guideAnswers.risk, guideAnswers.style].filter(Boolean),
    screening_criteria: { ...rec.screeningCriteria },
  })
  showGuideDialog.value = false
  showCreateDialog.value = true
  resetGuide()
}

const resetGuide = () => {
  guideStep.value = 1
  guideAnswers.risk = ''
  guideAnswers.style = ''
}

// 策略表单
const strategyForm = reactive({
  name: '',
  description: '',
  applicable_markets: ['A股'],
  tags: [] as string[],
  screening_criteria: {
    pe_max: undefined as number | undefined,
    roe_min: undefined as number | undefined,
    rsi_min: undefined as number | undefined,
    rsi_max: undefined as number | undefined,
    ma_trend: undefined as string | undefined,
  },
})

// 验证规则
const strategyRules: FormRules = {
  name: [{ required: true, message: '请输入策略名称', trigger: 'blur' }],
}

// 加载策略列表
const loadStrategies = async () => {
  loading.value = true
  try {
    const response = await investmentApi.listStrategies()
    if (response.success) {
      strategies.value = response.data.items || []
    }
  } catch (error) {
    ElMessage.error('加载策略列表失败')
  } finally {
    loading.value = false
  }
}

// 编辑策略
const editStrategy = (strategy: any) => {
  editingStrategy.value = strategy
  Object.assign(strategyForm, {
    name: strategy.name,
    description: strategy.description,
    applicable_markets: strategy.applicable_markets || ['A股'],
    tags: strategy.tags || [],
    screening_criteria: { ...strategy.screening_criteria },
  })
  showCreateDialog.value = true
}

// 保存策略
const saveStrategy = async () => {
  if (!strategyFormRef.value) return

  await strategyFormRef.value.validate(async (valid) => {
    if (!valid) return

    saving.value = true
    try {
      const response = editingStrategy.value
        ? await investmentApi.updateStrategy(editingStrategy.value.strategy_id, strategyForm)
        : await investmentApi.createStrategy(strategyForm)

      if (response.success) {
        ElMessage.success(editingStrategy.value ? '策略更新成功' : '策略创建成功')
        showCreateDialog.value = false
        resetForm()
        loadStrategies()
      }
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '保存失败')
    } finally {
      saving.value = false
    }
  })
}

// 切换策略状态
const toggleStatus = async (strategy: any) => {
  try {
    const action = strategy.status === 'active' ? 'disable' : 'enable'
    const response = await investmentApi.toggleStrategy(strategy.strategy_id, action)

    if (response.success) {
      ElMessage.success(`策略已${strategy.status === 'active' ? '停用' : '启用'}`)
      loadStrategies()
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '操作失败')
  }
}

// 任务确认向导：打开
const showTaskWizard = ref(false)
const taskWizardType = ref<'screening' | 'checkup'>('screening')
const taskWizardStrategy = ref<any>(null)
const taskWizardUseProfile = ref(true)
const creatingTask = ref(false)
const currentProfileId = ref<string | null>(null)

const loadCurrentProfileId = async () => {
  try {
    const response = await investmentApi.getProfile()
    currentProfileId.value = response.data?.id || null
  } catch {
    currentProfileId.value = null
  }
}

const taskWizardTitle = computed(() =>
  taskWizardType.value === 'screening' ? '确认发起策略选股' : '确认发起策略体检'
)

const hasScreeningCriteria = computed(() => {
  const c = taskWizardStrategy.value?.screening_criteria
  return !!(c && (c.pe_max || c.roe_min || c.ma_trend))
})

const openTaskWizard = (command: string, strategy: any) => {
  taskWizardType.value = command as 'screening' | 'checkup'
  taskWizardStrategy.value = strategy
  taskWizardUseProfile.value = !!currentProfileId.value
  showTaskWizard.value = true
}

// 确认发起任务
const confirmTaskWizard = async () => {
  const strategy = taskWizardStrategy.value
  if (!strategy) return

  creatingTask.value = true
  try {
    const response = await investmentApi.createTask(taskWizardType.value, {
      strategy_id: strategy.strategy_id,
      profile_id: taskWizardUseProfile.value ? currentProfileId.value : null,
    })

    if (response.success) {
      const taskId = response.data.task_id
      ElMessage.success(`${taskWizardType.value === 'screening' ? '选股' : '体检'}任务已创建`)
      showTaskWizard.value = false

      const routeName = taskWizardType.value === 'screening' ? 'ScreeningResults' : 'CheckupResults'
      router.push({ name: routeName, params: { taskId } })
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '创建任务失败')
  } finally {
    creatingTask.value = false
  }
}

// 重置表单
const resetForm = () => {
  editingStrategy.value = null
  Object.assign(strategyForm, {
    name: '',
    description: '',
    applicable_markets: ['A股'],
    tags: [],
    screening_criteria: {
      pe_max: undefined,
      roe_min: undefined,
      rsi_min: undefined,
      rsi_max: undefined,
      ma_trend: undefined,
    },
  })
  strategyFormRef.value?.resetFields()
}

onMounted(() => {
  loadStrategies()
  loadCurrentProfileId()
})
</script>

<style scoped>
.strategy-management {
  padding: 20px;
}

.guide-entry-card {
  margin-bottom: 16px;
  background-color: #f5f9ff;
}

.guide-entry {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.guide-entry-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.guide-entry-text span {
  font-size: 13px;
  color: #909399;
}

.template-strategy-card {
  margin-bottom: 16px;
}

.strategy-template-list {
  display: flex;
  gap: 16px;
}

.strategy-template-item {
  flex: 1;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.strategy-template-item:hover {
  border-color: #409EFF;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.strategy-template-name {
  font-weight: 600;
  color: #303133;
  margin-bottom: 6px;
}

.strategy-template-desc {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}

.strategy-template-tip {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.range-input {
  display: flex;
  align-items: center;
  gap: 8px;
}

.guide-step {
  padding: 20px 0;
}

.guide-question {
  font-weight: 600;
  color: #303133;
  margin-bottom: 16px;
}

.guide-options {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.guide-result-body {
  text-align: left;
}

.guide-evidence {
  margin-top: 12px;
  background: #f5f7fa;
  border-radius: 8px;
  padding: 12px 16px;
}

.guide-evidence-row {
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}

.task-wizard .form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.wizard-muted {
  color: #909399;
  font-size: 13px;
}
</style>
