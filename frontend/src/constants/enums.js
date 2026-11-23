export const Role = Object.freeze({ VIEWER: 'viewer', ANALYST: 'analyst', SUPERVISOR: 'supervisor' });
export const RunStatus = Object.freeze({
  QUEUED: 'queued', SUCCEEDED: 'succeeded', FAILED: 'failed', BLOCKED: 'blocked', SUPERSEDED: 'superseded',
});
export const Decision = Object.freeze({ APPROVED: 'approved', RETURNED: 'returned' });
export const Procedure = Object.freeze({ OLD: 'old', NEW: 'new' });
export const roleName = {viewer: '只读查看', analyst: '业务分析员', supervisor: '复核负责人'};
export const statusName = {
  queued: '等待重算', succeeded: '待复核', failed: '计算失败', blocked: '缺单受阻', superseded: '已作废',
  approved: '已签核', returned: '已退回',
};
export const procedureName = {old: '旧规程', new: '新规程'};
export const ticketStateName = {
  valid: '有效', withdrawn: '已撤回', replaced: '已被更正', applied: '生效',
  superseded: '已失效', unresolved: '待核对引用', conflict: '更正撤回冲突',
};
