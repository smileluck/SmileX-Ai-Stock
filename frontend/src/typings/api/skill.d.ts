declare namespace Api {
  /** AI 技能包管理 */
  namespace Skill {
    /** 技能记录（status 已由后端序列化为 '1'/'2'） */
    interface Skill {
      id: number;
      /** 技能编码（唯一，创建后不可修改） */
      code: string;
      name: string;
      /** 技能指令内容（启用后注入 Agent 系统提示词） */
      content: string;
      description: string | null;
      status: Common.EnableStatus | null;
      /** 排序（注入提示词的优先级，越小越靠前） */
      sort: number;
      created_at: string;
      updated_at: string | null;
    }

    /** 列表查询参数 */
    type QueryParams = CommonType.RecordNullable<
      {
        name: string;
        code: string;
        status: Common.EnableStatus;
      } & Common.CommonSearchParams
    >;

    /** 技能分页列表 */
    type SkillList = Common.PaginatingQueryRecord<Skill>;

    /** 新增请求体 */
    interface CreatePayload {
      code: string;
      name: string;
      content: string;
      description?: string | null;
      status: boolean;
      sort: number;
    }

    /** 编辑请求体（code 不可修改） */
    type UpdatePayload = Partial<Omit<CreatePayload, 'code'>>;
  }
}
