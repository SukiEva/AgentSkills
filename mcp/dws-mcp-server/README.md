# dws-mcp-server

基于 `FastMCP` 的华为云 DWS 诊断型 MCP Server，提供以下能力：

- 执行 SQL（默认只允许只读语句）
- `EXPLAIN / EXPLAIN ANALYZE / EXPLAIN PERFORMANCE`
- 列出 Schema 与表
- 获取表 DDL 与列定义
- 分析表结构、表大小、分布/分区线索
- 分析索引定义、索引使用情况、疑似重复/低价值索引
- 分析表空间碎片、脏页率、死元组比例

## 目录结构

```text
mcp/dws-mcp-server
├── pyproject.toml
├── README.md
└── src/dws_mcp_server
    ├── __init__.py
    ├── __main__.py
    ├── config.py
    ├── database.py
    ├── queries.py
    ├── server.py
    └── service.py
```

## 安装

统一使用 `uv` 管理 Python 版本、虚拟环境和依赖。

```bash
cd /Users/Suki/Documents/WorkSpace/Claude/AgentSkills/mcp/dws-mcp-server
uv python install 3.10
uv sync
```

说明：

- 项目目录下提供了 `.python-version`，默认固定到 `3.10`
- `uv sync` 会自动创建并维护 `.venv`
- 不需要再手动创建虚拟环境或单独安装依赖
- 由于 `FastMCP` 官方当前要求 `Python >=3.10`，这个子项目不能安全声明为 `>=3.9`

## 环境变量

至少需要配置以下变量：

```bash
export DWS_HOST="127.0.0.1"
export DWS_PORT="8000"
export DWS_DATABASE="postgres"
export DWS_USER="dbadmin"
export DWS_PASSWORD="******"
```

可选变量：

```bash
export DWS_SSLMODE="prefer"
export DWS_CONNECT_TIMEOUT="10"
export DWS_STATEMENT_TIMEOUT_MS="120000"
export DWS_DEFAULT_ROW_LIMIT="200"
export DWS_MAX_ROW_LIMIT="2000"
export DWS_APP_NAME="dws-mcp-server"
export DWS_ALLOW_MUTATION="false"
```

也可以直接复制仓库里的 `.env.example` 作为本地环境模板。

说明：

- `DWS_ALLOW_MUTATION=false` 时，仅允许 `SELECT / SHOW / VALUES / EXPLAIN` 等只读语句。
- 如需执行 `INSERT / UPDATE / DELETE / DDL`，必须同时：
  - 设置 `DWS_ALLOW_MUTATION=true`
  - 调用工具时显式传入 `allow_mutation=true`

## 启动

默认使用 `stdio` 传输：

```bash
cd /Users/Suki/Documents/WorkSpace/Claude/AgentSkills/mcp/dws-mcp-server
set -a
source .env
set +a
uv run dws-mcp-server
```

或：

```bash
uv run python -m dws_mcp_server
```

如果你想按 FastMCP 项目配置启动，也可以：

```bash
uv run fastmcp run fastmcp.json
```

## 主要工具

- `ping`
- `list_schemas`
- `list_tables`
- `execute_sql`
- `explain_sql`
- `get_table_ddl`
- `analyze_table_structure`
- `analyze_table_indexes`
- `analyze_table_storage`

## 推荐接入示例

如果你要把它挂到 MCP Client，可使用类似配置：

```json
{
  "mcpServers": {
    "dws-mcp-server": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/Users/Suki/Documents/WorkSpace/Claude/AgentSkills/mcp/dws-mcp-server",
        "dws-mcp-server"
      ],
      "env": {
        "DWS_HOST": "127.0.0.1",
        "DWS_PORT": "8000",
        "DWS_DATABASE": "postgres",
        "DWS_USER": "dbadmin",
        "DWS_PASSWORD": "******",
        "DWS_ALLOW_MUTATION": "false"
      }
    }
  }
}
```

## 设计说明

这个实现参考了 `huaweicloud_dws_mcp_inner` 的基础方向，但做了两点增强：

1. 明确分离“通用 SQL 执行”和“诊断分析工具”，方便后续扩展。
2. 在元数据能力之外，增加了面向 DWS 运维诊断的索引分析和空间碎片分析。

## 已知限制

- `EXPLAIN PERFORMANCE`、`pg_get_tabledef`、`PGXC_STAT_TABLE_DIRTY` 等能力与 DWS 版本强相关，服务内已做兼容降级，但不同集群上返回字段可能略有差异。
- 空间碎片分析优先读取 DWS 专有视图；若视图不存在，会退化为 `pg_stat_user_tables` 级别的死元组评估。
