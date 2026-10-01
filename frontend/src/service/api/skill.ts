import { request } from '../request';

/** ==================== Skills 管理 API ==================== */

/** 获取技能分页列表 */
export function fetchGetSkillList(params?: Api.Skill.QueryParams) {
  return request<Api.Skill.SkillList>({
    url: '/admin/skill/list',
    method: 'get',
    params
  });
}

/** 新增技能 */
export function fetchCreateSkill(data: Api.Skill.CreatePayload) {
  return request<Api.Skill.Skill>({
    url: '/admin/skill/add',
    method: 'post',
    data
  });
}

/** 更新技能（部分字段，code 不可改） */
export function fetchUpdateSkill(id: number, data: Api.Skill.UpdatePayload) {
  return request<Api.Skill.Skill>({
    url: `/admin/skill/${id}`,
    method: 'put',
    data
  });
}

/** 启用/禁用技能 */
export function fetchUpdateSkillStatus(id: number, status: boolean) {
  return request<Api.Skill.Skill>({
    url: `/admin/skill/${id}/status`,
    method: 'put',
    data: { status }
  });
}

/** 删除技能 */
export function fetchDeleteSkill(id: number) {
  return request<null>({
    url: `/admin/skill/${id}`,
    method: 'delete'
  });
}
