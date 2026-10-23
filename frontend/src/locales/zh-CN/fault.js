// FaultSolutionView 的文案。客户侧方案页与后台阅读面板共用同一个组件，
// 所以这块文案必须两边一致，不要在任何一侧覆盖。
export default {
  published: '已发布',
  draft: '未发布',
  needsPro: '需专业',
  proAlert: '该故障建议由专业人员处理，请勿自行拆机',
  meta: '{product} / {part}',
  updatedAt: '更新于 {date}',
  symptom: '现象描述',
  rootCause: '可能原因',
  requiredTools: '所需工具',
  steps: '排查步骤',
  noSteps: '暂无分步说明',
  attachments: '相关附件',
  none: '暂无',
  copy: {
    warning: '⚠️ 该故障建议由专业人员处理，请勿自行拆机',
    title: '【{title}】',
    meta: '产品：{product} / {part}',
    symptom: '现象：{text}',
    rootCause: '可能原因：{text}',
    tools: '所需工具：{text}',
    steps: '处理步骤：',
    imageMarker: '   [含示意图]',
    link: '完整图文方案：{url}',
    notPublished: '（该方案尚未发布，配图请在系统内查看）'
  },
}
