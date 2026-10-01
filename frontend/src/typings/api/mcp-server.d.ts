declare namespace Api {
  /** 外部 MCP 服务管理 */
  namespace McpServer {
    /** MCP 服务记录 */
    interface Server {
      id: number;
      /** 服务编码（唯一，创建后不可修改） */
      code: string;
      name: string;
      url: string;
      /** 请求头（鉴权等），可选 */
      headers: Record<string, string> | null;
      enabled: boolean;
      /** 请求超时（秒） */
      timeout_s: number;
      remark: string | null;
      created_at: string;
      updated_at: string | null;
    }

    /** 列表查询参数（前端 enabled 使用 '1'/'2'，请求前转换为 boolean） */
    type QueryParams = CommonType.RecordNullable<
      {
        name: string;
        code: string;
        enabled: Common.EnableStatus;
      } & Common.CommonSearchParams
    >;

    /** MCP 服务分页列表 */
    type ServerList = Common.PaginatingQueryRecord<Server>;

    /** 新增请求体 */
    interface CreatePayload {
      code: string;
      name: string;
      url: string;
      headers?: Record<string, string> | null;
      enabled: boolean;
      timeout_s: number;
      remark?: string | null;
    }

    /** 编辑请求体（code 不可修改） */
    type UpdatePayload = Partial<Omit<CreatePayload, 'code'>>;

    /** 连通性测试结果 */
    interface TestResult {
      success: boolean;
      latency_ms: number;
      message: string;
      tool_count: number;
    }

    /** MCP 工具项 */
    interface ToolItem {
      name: string;
      description: string;
      input_schema: Record<string, any>;
    }
  }
}
