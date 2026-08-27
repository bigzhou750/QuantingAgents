<template>
  <div class="strategy-management">
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
              {{ tag }}
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
            <el-dropdown trigger="click" @command="(cmd: string) => handleCommand(cmd, row)">
              <el-button size="small" type="primary">
                执行<el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="screening">策略选股</el-dropdown-item>
                  <el-dropdown-item command="checkup">策略体检</el-dropdown-item>
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, ArrowDown } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import axios from 'axios'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const strategies = ref<any[]>([])
const showCreateDialog = ref(false)
const editingStrategy = ref<any>(null)
const strategyFormRef = ref<FormInstance>()

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
    const response = await axios.get('/api/investment/strategies')
    if (response.data.success) {
      strategies.value = response.data.data.items || []
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
      const url = editingStrategy.value
        ? `/api/investment/strategies/${editingStrategy.value.strategy_id}`
        : '/api/investment/strategies'
      const method = editingStrategy.value ? 'put' : 'post'

      const response = await axios[method](url, strategyForm)

      if (response.data.success) {
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
    const response = await axios.post(`/api/investment/strategies/${strategy.strategy_id}/${action}`)

    if (response.data.success) {
      ElMessage.success(`策略已${strategy.status === 'active' ? '停用' : '启用'}`)
      loadStrategies()
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '操作失败')
  }
}

// 处理执行命令
const handleCommand = async (command: string, strategy: any) => {
  try {
    const endpoint = command === 'screening' ? '/api/investment/screening-tasks' : '/api/investment/checkup-tasks'
    const response = await axios.post(endpoint, {
      strategy_id: strategy.strategy_id,
    })

    if (response.data.success) {
      const taskId = response.data.data.task_id
      ElMessage.success(`${command === 'screening' ? '选股' : '体检'}任务已创建`)

      // 跳转到结果页
      const route = command === 'screening' ? 'ScreeningResults' : 'CheckupResults'
      router.push({ name: route, params: { taskId } })
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '创建任务失败')
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
})
</script>

<style scoped>
.strategy-management {
  padding: 20px;
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
</style>
