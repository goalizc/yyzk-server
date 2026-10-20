<template>
  <el-card shadow="never">
    <template #header>后台骨架已就绪</template>
    <el-descriptions :column="1" border size="small">
      <el-descriptions-item label="当前阶段">S0（脚手架 + 鉴权）</el-descriptions-item>
      <el-descriptions-item label="已完成">登录、修改密码、路由守卫</el-descriptions-item>
      <el-descriptions-item label="待开发">
        产品 / 零件 / 故障知识库 / 工单 / 数据看板
      </el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>
