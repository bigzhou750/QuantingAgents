<template>
  <main class="public-page">
    <header class="public-header">
      <router-link class="brand" to="/">智能投研助手</router-link>
      <nav>
        <router-link to="/pricing">定价</router-link>
        <router-link to="/terms">服务条款</router-link>
        <a href="mailto:zh75067197@gmail.com">支持邮箱</a>
      </nav>
    </header>
    <article class="content">
      <p class="eyebrow">zhitouagent</p>
      <h1>隐私政策</h1>
      <p class="updated">更新日期：2026 年 9 月 9 日</p>

      <h2>1. 我们收集的信息</h2>
      <p>当你注册和使用服务时，我们会处理账户标识、邮箱、登录与操作记录、额度使用记录，以及你主动提交的研究问题、股票代码和报告内容。我们不会在没有必要性的情况下收集身份证件、银行卡密码或其他与研究服务无关的信息。</p>

      <h2>2. 使用目的</h2>
      <p>我们使用上述信息提供研究分析、任务执行、额度计费、安全审计、客户支持和产品改进。除非为了履行订单或遵守法律，我们不会将你的研究输入用于与提供服务无关的目的。</p>

      <h2>3. 模型与数据服务</h2>
      <p>为提供分析能力，必要的研究输入可能发送给你在平台中选择的模型服务商；行情、新闻和财务数据可能来自配置的数据源。你应在输入中避免提交不必要的个人信息、商业机密或其他敏感内容。</p>

      <h2>4. 第三方服务与共享</h2>
      <p>平台可能接入模型服务商、数据源、支付服务商和基础云服务商。我们仅在其完成服务所必需的范围内共享必要数据，并尽量要求其采取合理安全措施。除法律要求或你明确同意外，我们不会出售你的个人信息。</p>

      <h2>5. 日志与保留</h2>
      <p>系统会保留安全审计、任务状态、错误和计费记录，用于提供服务、排查故障、防止滥用和处理订单。数据保留期限以业务需要和适用法律要求为限。</p>

      <h2>6. 你的权利</h2>
      <p>你可以通过 <a href="mailto:zh75067197@gmail.com">zh75067197@gmail.com</a> 查询、更正或申请删除可识别的账户信息，也可以咨询数据处理范围。部分删除请求可能受订单、安全或法律保留要求限制。</p>

      <h2>7. 安全说明</h2>
      <p>我们会采取合理的访问控制、日志保护和配置隔离措施。任何网络服务都不能保证绝对安全；如发生可能影响个人信息的安全事件，我们会按适用要求在可行范围内通知并处理。</p>

      <h2>8. 敏感信息提示</h2>
      <p>请勿在研究输入中提交 API 密钥、密码、身份证号码、银行卡信息或其他不必要的敏感信息。我们对因你主动提交敏感信息造成的后果不承担超出合理范围的责任。</p>

      <h2>9. 政策更新与联系方式</h2>
      <p>我们可能更新本政策，并在本页面公布更新日期。隐私相关问题请联系 <a href="mailto:zh75067197@gmail.com">zh75067197@gmail.com</a>。</p>
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
