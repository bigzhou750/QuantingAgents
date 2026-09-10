<template>
  <main class="public-page">
    <header class="public-header">
      <router-link class="brand" to="/">智能投研助手</router-link>
      <nav>
        <router-link to="/pricing">定价</router-link>
        <router-link to="/privacy">隐私政策</router-link>
        <a href="mailto:zh75067197@gmail.com">支持邮箱</a>
      </nav>
    </header>
    <article class="content">
      <p class="eyebrow">zhitouagent</p>
      <h1>服务条款</h1>
      <p class="updated">生效日期：2026 年 9 月 9 日</p>

      <h2>1. 服务范围</h2>
      <p>智能投研助手提供股票信息整理、研究分析、自然语言研究工作台、报告和学习工具。服务内容可能因数据源、模型供应商和系统状态变化，具体可用功能以平台实际展示为准。</p>

      <h2>2. 账号与注册</h2>
      <p>注册时请提供真实、有效的用户名和邮箱，并妥善保管账号信息。你应对账号下的登录、设置、研究输入和订单操作负责；发现账号异常时应尽快联系支持邮箱。</p>

      <h2>3. 合理使用</h2>
      <p>你不得利用服务进行违法活动、操纵市场、欺诈、批量滥用接口、绕过访问控制或提交他人的敏感信息。不得以干扰服务正常运行的方式使用平台，也不得将平台输出用于误导他人或冒充专业投资意见。</p>

      <h2>4. 分析结果限制</h2>
      <p>平台输出由数据、模型和用户输入共同影响，可能不完整、延迟或错误。所有内容仅供研究和信息参考，不构成投资、证券、交易、法律、税务或收益保证。你应自行判断并承担研究决策责任。</p>

      <h2>5. 额度、支付与退款</h2>
      <p>套餐、额度、订单和退款以平台当前展示及订单记录为准。额度充值属于即时到账的数字服务，除重复扣款、平台确认的服务中断或适用法律另有规定外，一般不提供无理由退款。</p>
      <p>退款申请请提供账户邮箱、订单号或流水号以及退款原因，发送至 <a href="mailto:zh75067197@gmail.com">zh75067197@gmail.com</a>。我们会在 2 个工作日内确认，并按实际订单状态和支付渠道规则处理。因第三方支付、数据源或模型供应商故障导致的延迟，会在可行时通过任务状态或支持邮箱告知。</p>

      <h2>6. 第三方服务</h2>
      <p>平台可能调用模型服务商、行情新闻数据源和支付服务商等第三方服务。第三方服务的可用性、价格和条款可能变化；这些变化不影响你与平台之间订单记录的核对，但平台不为其独立故障或政策承担超出合理服务的责任。</p>

      <h2>7. 知识产权</h2>
      <p>平台的界面、产品名称、文档和默认文案归我们或相应权利人所有。你输入的研究内容归你所有；为完成分析所必需，平台会在提供服务范围内处理这些输入。未经许可不得复制、转售或反向工程平台核心服务。</p>

      <h2>8. 责任限制</h2>
      <p>在法律允许的范围内，平台不对因数据延迟、模型错误、第三方服务故障、网络或系统维护造成的间接损失承担责任。前述责任限制不排除因平台故意或重大过失造成的法定责任。</p>

      <h2>9. 服务变更与终止</h2>
      <p>平台可能根据业务需要调整功能、套餐、配额或停止不活跃账号的访问。若你违反本条款，我们可以在通知后限制或终止服务；套餐余额的处理会以订单记录和当时公布的政策为准。</p>

      <h2>10. 条款更新</h2>
      <p>我们可能不时更新本条款。更新后会在本页面公布生效日期；继续使用服务视为接受更新后的条款。重要变更会在可行时通过站内通知或支持邮箱告知。</p>

      <h2>11. 联系我们</h2>
      <p>服务问题、订单问题或条款咨询请联系 <a href="mailto:zh75067197@gmail.com">zh75067197@gmail.com</a>。</p>
    </article>
  </main>
</template>
<style scoped>
.public-page { min-height: 100vh; background: #101214; color: #e5e7eb; }
.public-header { display: flex; justify-content: space-between; align-items: center; gap: 24px; padding: 24px max(24px, calc((100vw - 1080px) / 2)); border-bottom: 1px solid #2b3036; }
.brand { color: #fff; font-weight: 700; text-decoration: none; }
nav { display: flex; flex-wrap: wrap; gap: 18px; }
nav a { color: #aeb7c2; text-decoration: none; }
.content { max-width: 820px; margin: auto; padding: 64px 24px 96px; }
.eyebrow { color: #5ec4b6; text-transform: uppercase; }
h1 { font-size: 42px; margin: 12px 0; }
h2 { margin-top: 34px; font-size: 20px; }
p { line-height: 1.8; color: #b9c0c8; }
a { color: #6fd3c4; }
.updated { font-size: 13px; }
@media (max-width: 768px) {
  .public-header { align-items: flex-start; flex-direction: column; padding: 18px 20px; }
  .content { padding: 44px 20px 72px; }
  h1 { font-size: 32px; }
}
</style>
