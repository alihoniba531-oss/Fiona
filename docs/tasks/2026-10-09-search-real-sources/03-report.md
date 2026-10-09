# 搜索与旅行真实来源实现报告

规格：[02-spec.md](./02-spec.md)。实施日期：2026-10-09。

> 规格 5.1–5.8 的实现已完成，验收尚未全部满足：第 6.5 节全量后端测试退出 1，结果为 **1 failed, 2118 passed, 11 warnings, 5 errors in 58.66s**。6 个既有测试在绑定本机回环端口时被沙箱以 EPERM 拒绝，需要在沙箱外重跑全部 2124 个测试。新增真实来源测试单跑 **72 passed**，前端类型检查退出 0，Lint 为 **0 errors / 25 warnings**。

## 修改文件

| 文件 | 改动 |
|---|---|
| `backend/tools/native_search.py`（新增） | 共用原生搜索、真实来源整理与引用角标清理 |
| `backend/tools/web_search.py` | 原生搜索调用、真实来源与无来源错误卡 |
| `backend/tools/travel_plan.py` | 原生搜索调用、行程标题/要点清理与无来源交付 |
| `backend/tests/test_search_real_sources.py`（新增） | 真实来源与失败边界测试，统一禁止未打桩网络 |
| `backend/tests/test_spec_bugfixes.py` | 仅调整允许的畸形 JSON 测试打桩与来源断言 |
| `backend/tests/test_beta_billing.py` | 仅调整允许的纯文本工具回复测试打桩 |
| `frontend/lib/open.ts` | 新增绝对 HTTP(S) 外链格式校验 |
| `frontend/components/ChatBubble.tsx` | 可点击来源标题、站点与安全外链入口 |
| `frontend/app/page.tsx` | 通用卡错误气泡使用错误说明 |
| `README.md` | 当前来源能力、原生接口超时例外和卡片不落库限制 |
| `docs/ARCHITECTURE.md` | 原生搜索数据流、来源安全边界与前端/历史行为 |
| `docs/DEPLOYMENT.md` | 超时/重试配置例外和部署后来源抽查事项 |
| `PLAN.md` | 本轮能力、当前超时边界与持久化限制 |
| `CLAUDE.md` | 开发上下文中的接口、来源和卡片展示事实 |
| `docs/tasks/2026-10-09-search-real-sources/03-report.md`（新增） | 实现、任务对照、实际验收输出和人工项 |

## 功能与规格 5.1–5.8 对照

| 任务 | 实现对应 | 验证对应 |
|---|---|---|
| 5.1 | `native_search.grounded_search` 从环境读取 Key、复用模块级 `_request_search`；处理异常、响应形状和截断；容错解析 JSON；复制并规范化来源编号；从原生搜索结果经 `_search_sources` 公网 HTTP(S) 格式校验、去重与引用优先排序，只保留指定字段；`strip_citations` 删除指定角标并收拢空白与中文标点 | 新增测试覆盖真实原生形状、模型 URL 排除、排序/去重、URL 过滤、无原地修改、缺 Key、异常与角标 |
| 5.2 | 普通搜索改为原生调用，来源只用真实搜索结果；要点去角标；无真实来源错误且不计费；保留天气分流与今日日期指令 | 新增搜索与计费回归、天气分流测试；第 6 节天气 diff、兼容客户端 grep 与全量后端测试 |
| 5.3 | 旅行改为原生调用，标题按字符串安全处理并与要点一起去角标；无来源仍交付建议，空 sources/URL；朗读输入已清理 | 新增旅行、朗读和历史摘要测试，保留原错误语义的兼容回归 |
| 5.4 | `toSafeExternalUrl` 只接受绝对、带 hostname、无凭据、长度不超过 2048 的 HTTP(S) URL | TypeScript/ESLint 及代码检查；既有外链函数行为保持 |
| 5.5 | 通用卡要点下方显示最多 5 个安全来源；标题回落、站点/hostname、图标、触控区、aria-label 和现有 token；来源按钮调用 `openExternal`；有来源时隐藏重复表头 URL | TypeScript/ESLint、来源与 `openExternal` grep；界面截图留待沙箱外 |
| 5.6 | 只调整通用错误卡 tip，优先首条错误说明，否则固定可靠结果兜底 | TypeScript/ESLint 与 diff 检查；天气/旅行 tip 保留 |
| 5.7 | 新增禁止真实网络的测试；现有测试只改规格指定的两处打桩与断言，其余受保护测试不动 | 新增测试单跑、全量后端与受保护文件 diff；函数范围复核 |
| 5.8 | 全库扫描事实陈述点并更新五份允许文档；说明原生 qwen-plus 强制联网、真实来源格式校验、固定 30 秒 socket 超时无重试与环境变量例外、前端点击来源及卡片不落库 | 文档 diff 与事实 rg 复查；报告不含本机绝对路径 |

## 第 6 节验收记录

命令均在规格指定目录执行。运行后端命令前将既有 `backend/.venv/bin` 加入 PATH，未安装依赖，命令本身保持规格原样。新增测试包含 72 个参数化测试用例，预期总数为 `2052 + 72 = 2124`。为遵守文档不得写入本机绝对路径的要求，原始输出仅将仓库根目录的机器路径前缀移除，显示仓库相对路径；Homebrew Python 标准库目录前缀替换为 `<Python标准库>/`。日志、警告、错误正文、行号、规则和退出码保持实际结果。无匹配时 `grep` 退出码为 1，这是第 6.3 / 6.4 的预期结果；通过条件结合输出判断，不将所有命令都泛称为退出码 0。

### 6.1 修改范围

目录：仓库根目录。命令：`git status --porcelain`。

实际输出：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/tests/test_beta_billing.py
 M backend/tests/test_spec_bugfixes.py
 M backend/tools/travel_plan.py
 M backend/tools/web_search.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatBubble.tsx
 M frontend/lib/open.ts
?? backend/tests/test_search_real_sources.py
?? backend/tools/native_search.py
?? docs/tasks/2026-10-09-search-real-sources/
```

退出码：`0`。

### 6.2 受保护文件不变

目录：仓库根目录。

```bash
git diff --exit-code -- backend/tests/test_card_detail.py backend/tests/test_beijing_time.py backend/tools/card_detail.py backend/tools/topic_expand.py backend/tools/visual_search.py backend/utils/safe_http.py
```

实际输出：无输出。

退出码：`0`。

### 6.3 天气分流未改

目录：仓库根目录。命令：`git diff -U0 -- backend/tools/web_search.py | grep -n '_search_weather_direct'`。

实际输出：无输出。

退出码：`1`。

### 6.4 兼容客户端已移除

目录：仓库根目录。命令：`grep -n "_get_client" backend/tools/web_search.py backend/tools/travel_plan.py`。

实际输出：无输出。

退出码：`1`。

### 6.5 后端全量测试

目录：`backend/`。命令：`python -m pytest -q`。

实际输出：

```text
........................................................................ [  3%]
........................................................................ [  6%]
........................................................................ [ 10%]
........................................................................ [ 13%]
........................................................................ [ 16%]
........................................................................ [ 20%]
........................................................................ [ 23%]
........................................................................ [ 27%]
........................................................................ [ 30%]
........................................................................ [ 33%]
........................................................................ [ 37%]
........................................................................ [ 40%]
........................................................................ [ 44%]
........................................................................ [ 47%]
.......................................................................E [ 50%]
F....................................................................... [ 54%]
........................................................................ [ 57%]
........................................................................ [ 61%]
........................................................................ [ 64%]
........................................................................ [ 67%]
........................................................................ [ 71%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 81%]
...................................EEE.E................................ [ 84%]
........................................................................ [ 88%]
........................................................................ [ 91%]
........................................................................ [ 94%]
........................................................................ [ 98%]
....................................                                     [100%]
==================================== ERRORS ====================================
_ ERROR at setup of test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive _

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10ecab540>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x10ff69940>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python标准库>/socketserver.py:478: PermissionError
_____ ERROR at setup of test_drip_response_obeys_total_wall_clock_deadline _____

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x110a9dc50>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x1109bf110>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python标准库>/socketserver.py:478: PermissionError
_________ ERROR at setup of test_fast_response_and_redirect_still_work _________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10f0b9c50>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x110a434d0>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python标准库>/socketserver.py:478: PermissionError
______ ERROR at setup of test_drip_headers_obey_total_wall_clock_deadline ______

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10eca9400>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x1109883e0>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python标准库>/socketserver.py:478: PermissionError
___ ERROR at setup of test_four_stuck_resolutions_do_not_block_another_fetch ___

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10e99df60>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x110989f30>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python标准库>/socketserver.py:478: PermissionError
=================================== FAILURES ===================================
_________ test_stop_disconnects_async_upstream_and_releases_user_slot __________

client = <starlette.testclient.TestClient object at 0x10fe8e140>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x1105f3e70>

    def test_stop_disconnects_async_upstream_and_releases_user_slot(client, monkeypatch):
        import services.exchange_service as service
    
        async def start_server():
            entered, disconnected = asyncio.Event(), asyncio.Event()
    
            async def handler(reader, writer):
                try:
                    headers = await reader.readuntil(b"\r\n\r\n")
                    length = 0
                    for line in headers.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            length = int(line.split(b":", 1)[1].strip())
                    if length:
                        await reader.readexactly(length)
                    entered.set()
                    await reader.read(1)
                    disconnected.set()
                finally:
                    writer.close()
                    await writer.wait_closed()
    
            server = await asyncio.start_server(handler, "127.0.0.1", 0)
            return server, entered, disconnected
    
        async def wait_event(event):
            await asyncio.wait_for(event.wait(), timeout=5)
    
>       server, entered, disconnected = client.portal.call(start_server)
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_exchange_isolation.py:151: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv/lib/python3.14/site-packages/anyio/from_thread.py:338: in call
    return cast(T_Retval, self.start_task_soon(func, *args).result())
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python标准库>/concurrent/futures/_base.py:454: in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
<Python标准库>/concurrent/futures/_base.py:396: in __get_result
    raise self._exception
.venv/lib/python3.14/site-packages/anyio/from_thread.py:263: in _call_func
    retval = await retval_or_awaitable
             ^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_exchange_isolation.py:145: in start_server
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python标准库>/asyncio/streams.py:84: in start_server
    return await loop.create_server(factory, host, port, **kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <_UnixSelectorEventLoop running=True closed=False debug=False>
protocol_factory = <function start_server.<locals>.factory at 0x11086d6f0>
host = '127.0.0.1', port = 0, family = <AddressFamily.AF_UNSPEC: 0>
flags = <AddressInfo.AI_PASSIVE: 1>
sock = <socket.socket [closed] fd=-1, family=2, type=1, proto=6>, backlog = 100
ssl = None, reuse_address = True, reuse_port = None, keep_alive = None
ssl_handshake_timeout = None, ssl_shutdown_timeout = None, start_serving = True

    async def create_server(
            self, protocol_factory, host=None, port=None,
            *,
            family=socket.AF_UNSPEC,
            flags=socket.AI_PASSIVE,
            sock=None,
            backlog=100,
            ssl=None,
            reuse_address=None,
            reuse_port=None,
            keep_alive=None,
            ssl_handshake_timeout=None,
            ssl_shutdown_timeout=None,
            start_serving=True):
        """Create a TCP server.
    
        The host parameter can be a string, in that case the TCP server is
        bound to host and port.
    
        The host parameter can also be a sequence of strings and in that
        case the TCP server is bound to all hosts of the sequence.  If
        a host appears multiple times (possibly indirectly e.g. when
        hostnames resolve to the same IP address), the server is only bound
        once to that host.
    
        Return a Server object which can be used to stop the service.
    
        This method is a coroutine.
        """
        if isinstance(ssl, bool):
            raise TypeError('ssl argument must be an SSLContext or None')
    
        if ssl_handshake_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_handshake_timeout is only meaningful with ssl')
    
        if ssl_shutdown_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_shutdown_timeout is only meaningful with ssl')
    
        if sock is not None:
            _check_ssl_socket(sock)
    
        if host is not None or port is not None:
            if sock is not None:
                raise ValueError(
                    'host/port and sock can not be specified at the same time')
    
            if reuse_address is None:
                reuse_address = os.name == "posix" and sys.platform != "cygwin"
            sockets = []
            if host == '':
                hosts = [None]
            elif (isinstance(host, str) or
                  not isinstance(host, collections.abc.Iterable)):
                hosts = [host]
            else:
                hosts = host
    
            fs = [self._create_server_getaddrinfo(host, port, family=family,
                                                  flags=flags)
                  for host in hosts]
            infos = await tasks.gather(*fs)
            infos = set(itertools.chain.from_iterable(infos))
    
            completed = False
            try:
                for res in infos:
                    af, socktype, proto, canonname, sa = res
                    try:
                        sock = socket.socket(af, socktype, proto)
                    except socket.error:
                        # Assume it's a bad family/type/protocol combination.
                        if self._debug:
                            logger.warning('create_server() failed to create '
                                           'socket.socket(%r, %r, %r)',
                                           af, socktype, proto, exc_info=True)
                        continue
                    sockets.append(sock)
                    if reuse_address:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                    # Since Linux 6.12.9, SO_REUSEPORT is not allowed
                    # on other address families than AF_INET/AF_INET6.
                    if reuse_port and af in (socket.AF_INET, socket.AF_INET6):
                        _set_reuseport(sock)
                    if keep_alive:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_KEEPALIVE, True)
                    # Disable IPv4/IPv6 dual stack support (enabled by
                    # default on Linux) which makes a single socket
                    # listen on both address families.
                    if (_HAS_IPv6 and
                            af == socket.AF_INET6 and
                            hasattr(socket, 'IPPROTO_IPV6')):
                        sock.setsockopt(socket.IPPROTO_IPV6,
                                        socket.IPV6_V6ONLY,
                                        True)
                    try:
                        sock.bind(sa)
                    except OSError as err:
                        msg = ('error while attempting '
                               'to bind on address %r: %s'
                               % (sa, str(err).lower()))
                        if err.errno == errno.EADDRNOTAVAIL:
                            # Assume the family is not enabled (bpo-30945)
                            sockets.pop()
                            sock.close()
                            if self._debug:
                                logger.warning(msg)
                            continue
>                       raise OSError(err.errno, msg) from None
E                       PermissionError: [Errno 1] error while attempting to bind on address ('127.0.0.1', 0): [errno 1] operation not permitted

<Python标准库>/asyncio/base_events.py:1637: PermissionError
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 2118 passed, 11 warnings, 5 errors in 58.66s
```

退出码：`1`。

### 6.6 新增测试单跑

目录：`backend/`。命令：`python -m pytest -q tests/test_search_real_sources.py`。

实际输出：

```text
........................................................................ [100%]
72 passed in 0.56s
```

退出码：`0`。

### 6.7 前端类型与 Lint

目录：`frontend/`。命令：`npx tsc --noEmit`。

实际输出：无输出。

退出码：`0`。

目录：`frontend/`。命令：`npx eslint .`。

实际输出：

```text
frontend/app/page.tsx
   143:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   234:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   402:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   455:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   456:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   457:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   467:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   468:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   469:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   470:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   473:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   479:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   480:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   784:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   878:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1302:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1322:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1330:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1351:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1393:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1489:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1838) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1937:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1977:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2247:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

frontend/app/plaza/page.tsx
  602:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 25 problems (0 errors, 25 warnings)
```

退出码：`0`。

### 6.8 安全外链调用

目录：`frontend/`。命令：`grep -n "toSafeExternalUrl" components/ChatBubble.tsx lib/open.ts`。

实际输出：

```text
components/ChatBubble.tsx:9:import { openExternal, toSafeExternalUrl } from "@/lib/open";
components/ChatBubble.tsx:249:            const url = toSafeExternalUrl(source.url);
lib/open.ts:30:export function toSafeExternalUrl(url: unknown): string | null {
```

退出码：`0`。

目录：`frontend/`。命令：`grep -n "openExternal" components/ChatBubble.tsx`。

实际输出：

```text
9:import { openExternal, toSafeExternalUrl } from "@/lib/open";
288:                        onClick={() => void openExternal(url)}
```

退出码：`0`。

## 补充范围复核

对修改路径白名单、两处现有测试函数之外的全部字节、受保护测试、两份 `_today_directive` 和天气分流另作复核：

实际输出：

```text
All changed paths are within the specification allowlist
backend/tests/test_spec_bugfixes.py: all bytes outside the allowed function unchanged
backend/tests/test_beta_billing.py: all bytes outside the allowed function unchanged
All protected existing test files unchanged
Both _today_directive functions unchanged
Weather dispatch unchanged
```

退出码：`0`。

`git diff --check`：无输出，退出码 `0`。

## 同一沙箱中的基线复现

另用 `git archive 5279935` 在仓库外的临时副本提取未修改基线（提取退出码 `0`），只复跑第 6.5 节受影响的六个原样测试节点，退出码 `1`。基线同样有 5 个 `ThreadingHTTPServer` setup 在 `bind` 时被拒绝，1 个 `asyncio.start_server` 在回环地址绑定时被拒绝；说明当前沙箱在原代码上也会复现相同六处失败，支持环境限制判断。该复现不能替代沙箱外的完整验收，第 6.5 节仍未满足。

原始输出摘录：

```text
FEEEEE                                                                   [100%]
E       PermissionError: [Errno 1] Operation not permitted
E                       PermissionError: [Errno 1] error while attempting to bind on address ('127.0.0.1', 0): [errno 1] operation not permitted
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 11 warnings, 5 errors in 0.71s
```

## 文档全库扫描与范围边界

使用 `rg` 扫描全库（包含隐藏文件，排除 `.git` 和依赖目录），并对非任务历史 Markdown 再做定向检索。查询覆盖 `DASHSCOPE_TIMEOUT_SECONDS`、`DASHSCOPE_MAX_RETRIES`、60 秒/重试/有限重试、`qwen-plus`、搜索/旅行来源、卡片落库/刷新等表述；复查了五份允许文档的全部相关陈述点。

已逐处同步：README 的当前能力与模型客户端默认值；架构文档的前端卡片、qwen-plus、原生来源数据流和运行边界；部署手册的环境配置例外与来源抽查；PLAN 的当前实现、历史客户端泛化陈述和近期前端限制；CLAUDE 的模型上下文与来源/抓取边界。

范围外 `backend/.env.example:16` 保留原有“模型请求默认 60 秒超时，失败最多重试 1 次”泛化注释，未修改；README 与部署手册已明确该配置对搜索/旅行原生调用不生效。其他任务历史只作扫描，不改写。`02-spec.md` 未修改。

## 未完成或人工确认

- 本单实现项无未完成；规格第 6.5 节仍未满足。完整后端测试中的 6 个既有测试在 loopback bind 阶段抛出 `PermissionError: [Errno 1] Operation not permitted`，未改动这些测试，也未绕过沙箱。须由 Claude 在沙箱外重跑 `python -m pytest -q`，确认全部 2124 个测试通过。
- 受影响节点为 `test_exchange_isolation.py` 的 `test_stop_disconnects_async_upstream_and_releases_user_slot`（FAILED）、`test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive`（ERROR），以及 `test_safe_http_deadline.py` 的 `test_drip_response_obeys_total_wall_clock_deadline`、`test_fast_response_and_redirect_still_work`、`test_drip_headers_obey_total_wall_clock_deadline`、`test_four_stuck_resolutions_do_not_block_another_fetch`（四项 ERROR）。完整错误栈见第 6.5 节。
- 按规格第 6 节，未运行 `npm run build` / `npm run dev`，未启动后端，未尝试真实网络请求。生产构建、真实 DashScope 原生接口抽查、浏览器/Tauri 来源点击与日夜间/手机界面截图由 Claude 在沙箱外完成。
- 卡片和来源不落库，刷新或切换会话后只保留文字摘要，是本单明确保留的限制。


## 返修 R1

依据：[05-fix-r1.md](./05-fix-r1.md)、[04-review.md](./04-review.md) 和原 [02-spec.md](./02-spec.md)。本节只追加本轮记录，前文全部字节保留。

R1-1–R1-4 的代码与现行文档修改已完成。真实来源测试从 72 增至 **112 个用例（新增 40）**，全部通过；TypeScript 退出 0，ESLint **0 errors / 25 warnings**。全量测试仍有同一沙箱的六处回环端口 EPERM：**1 failed, 2158 passed, 11 warnings, 5 errors in 56.72s**，退出 1，按返修规格第 7 条留待沙箱外重跑。第 5 条原文要求“无输出”的全 docs 扫描会自匹配不可修改的返修规格，实际有两行命中；本节保留实际结果和范围说明，未将所有验收无条件标为通过。

### 本轮修改文件

本轮没有新增文件；以下文件在首轮实现基础上修改：

| 文件 | 本轮变化 |
|---|---|
| `backend/tools/native_search.py` | 新增 `strip_urls`，清理模型正文中的链接并收拢空白 |
| `backend/tools/web_search.py` | 普通与非 JSON 回退要点清理 URL，拒绝结构对象和 bool 要点 |
| `backend/tools/travel_plan.py` | 标题、要点和回退行清理 URL，正文输入类型防御 |
| `backend/tests/test_search_real_sources.py` | 原 72 个用例逐字保留，追加 40 个 R1 用例 |
| `frontend/components/ChatBubble.tsx` | 来源标题/站点类型防御，箭头继承按钮颜色 |
| `README.md` | 四项原生调用的超时例外、分类模型和正文去 URL 能力 |
| `docs/ARCHITECTURE.md` | 正文清理与类型限制，原生调用范围、详情外层超时及分类模型 |
| `docs/DEPLOYMENT.md` | 四项原生调用的超时配置边界、分类模型与正文清理 |
| `PLAN.md` | 删除验收人员/流程说明，修正当前模型与超时范围 |
| `CLAUDE.md` | 开发上下文中的四项原生调用、分类模型和正文清理事实 |
| `docs/tasks/2026-10-09-search-real-sources/03-report.md` | 仅在末尾追加「返修 R1」记录 |

### R1-1–R1-4 逐项对应

| 要求 | 实现与功能 | 验证 |
|---|---|---|
| R1-1 | `strip_urls` 把 Markdown 链接转成显示文字，移除 HTTP(S) 与 www. 片段，并按现有引用清理规则收拢空格；搜索要点、旅行标题/要点和非 JSON 回退行依次先去角标再去 URL，清理后空条目丢弃；非字符串要点只保留非 bool 的 int/float，其余 dict/list/对象丢弃 | 新增 40 用例覆盖正文各类 URL、URL 独占条目、结构类型、旅行标题、朗读/历史摘要，以及 3.5% / v2.0 等非 URL 文字保留；112 用例单跑全过 |
| R1-2 | 来源按钮的 `ArrowUpRight` 去掉固定颜色内联 style，继承按钮的普通与 hover 文字颜色，其他样式保留 | 指定 style grep 无输出，TypeScript 与 Lint 通过 |
| R1-3 | `safeSources` 对 title 和 site_name 先检查字符串类型再 trim，异常值作为空串，继续按站点与 hostname 回落 | TypeScript 与 Lint 通过，代码检查 |
| R1-4 | 删除 PLAN 本单验收流程句；全库核对超时/重试、环境变量、热点分类与 qwen-plus 陈述，五份现行文档逐处写全搜索、旅行规划、热点展开、卡片详情的原生 30 秒 socket 无重试例外；详情路由外层 45 秒；热点分类 qwen3.8-flash 固定 8 秒无重试，热点展开 qwen-plus | PLAN grep 无输出；现行文档定向扫描无错误词组；直接核对 `routers/hot.py` 的 with_options(8.0, 0)、`llm.QWEN_MODEL` 和 `routers/cards.py` 的 45 秒 wait_for |

### 05-fix-r1 验收实际输出与退出码

验收证据汇编时间：`2026-10-09 10:50:01 UTC`（汇编时间，不是各条命令的精确执行时间）。第 5 条 grep 在本轮代码和五份现行文档完成后、追加本节之前执行。后端运行前仅将既有 `backend/.venv/bin` 加入 PATH，未安装依赖，命令保持规格原样。输出中的机器仓库前缀仅转换为仓库相对路径，Homebrew Python 标准库前缀仅显示为 `<Python标准库>/`；其余日志正文、行号、规则、结果与退出码保持实际内容。

#### R1验收1

目录：`仓库根目录`。

```bash
git status --porcelain
```

实际输出：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/tests/test_beta_billing.py
 M backend/tests/test_spec_bugfixes.py
 M backend/tools/travel_plan.py
 M backend/tools/web_search.py
 M docs/ARCHITECTURE.md
 M docs/DEPLOYMENT.md
 M frontend/app/page.tsx
 M frontend/components/ChatBubble.tsx
 M frontend/lib/open.ts
?? backend/tests/test_search_real_sources.py
?? backend/tools/native_search.py
?? docs/tasks/2026-10-09-search-real-sources/
```

退出码：`0`。

该输出显示首轮与 R1 的累积工作区变化。范围复核确认本轮只修改上表 11 个既有文件，未新增文件。

#### R1验收2

目录：`backend/`。

```bash
python -m pytest -q tests/test_search_real_sources.py
```

实际输出：

```text
........................................................................ [ 64%]
........................................                                 [100%]
112 passed in 0.51s
```

退出码：`0`。

#### R1验收3

目录：`仓库根目录`。

```bash
grep -n 'style={{ color: "var(--ink2)" }}' frontend/components/ChatBubble.tsx
```

实际输出：无输出。

退出码：`1`。

#### R1验收4

目录：`仓库根目录`。

```bash
grep -n "沙箱外" PLAN.md
```

实际输出：无输出。

退出码：`1`。

#### R1验收5

目录：`仓库根目录`。

```bash
grep -rn "热点分类/展开" README.md docs/ PLAN.md CLAUDE.md
```

实际输出：

```text
docs/tasks/2026-10-09-search-real-sources/05-fix-r1.md:35:3. **热点分类的模型写错了**：热点分类用的是 `qwen3.8-flash`（`backend/routers/hot.py` 使用 `llm.QWEN_MODEL`，`backend/llm.py` 中 `QWEN_MODEL = "qwen3.8-flash"`，8 秒超时、不重试），只有热点**展开**才用 `qwen-plus`。纠正 `docs/ARCHITECTURE.md` 模型清单里「`qwen-plus`：联网搜索、热点分类/展开和旅行规划」及 `CLAUDE.md`「搜索/热点/旅行 `qwen-plus`」等含混或错误表述；同样全库搜索「热点分类」「qwen-plus」的其他陈述。
docs/tasks/2026-10-09-search-real-sources/05-fix-r1.md:43:5. `grep -rn "热点分类/展开" README.md docs/ PLAN.md CLAUDE.md` 无输出。
```

退出码：`0`。

两行命中均来自不可修改的 `05-fix-r1.md:35 / :43`：分别是引用旧错误表述与验收命令本身。原命令扫描全部 docs 的“无输出”条件在保留规格的前提下无法成立。本节追加原命令和输出后，重新运行同一 grep 还会匹配本报告的命令/日志；上述两行输出记录的是追加前的实际扫描时点。需要确认该验收的预期对象是排除任务规格、评审与报告记录后的现行文档。现行五份文档的补充检查如下。

目录：`仓库根目录`。

```bash
rg -n '热点分类/展开' README.md docs/ARCHITECTURE.md docs/DEPLOYMENT.md PLAN.md CLAUDE.md
```

实际输出：无输出。

退出码：`1`。

#### R1验收6a

目录：`frontend/`。

```bash
npx tsc --noEmit
```

实际输出：无输出。

退出码：`0`。

#### R1验收6b

目录：`frontend/`。

```bash
npx eslint .
```

实际输出：

```text
frontend/app/page.tsx
   143:10  warning  'MiniCloudCard' is defined but never used                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   234:7   warning  'DEMO_MESSAGES' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   402:10  warning  'allUsers' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   455:9   warning  'nlsWsRef' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   456:9   warning  'mediaRecorderRef' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   457:9   warning  'audioCtxRef' is assigned a value but never used                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   467:10  warning  'peerRooms' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   468:10  warning  'activePeer' is assigned a value but never used                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   469:10  warning  'pendingMatches' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   470:10  warning  'cardPositions' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   473:10  warning  'peerConnected' is assigned a value but never used                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   479:10  warning  'myGender' is assigned a value but never used                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   480:10  warning  'matchPref' is assigned a value but never used                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   784:20  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   878:18  warning  '_' is defined but never used                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1302:9   warning  'saveUserSettings' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1322:9   warning  'handleCardExpire' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1330:9   warning  'handleAcceptCard' is assigned a value but never used                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1351:9   warning  'handleSkipCard' is assigned a value but never used                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1393:9   warning  'handleClearChat' is assigned a value but never used                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1489:9   warning  The 'handleSend' function makes the dependencies of useEffect Hook (at line 1838) change on every render. To fix this, wrap the definition of 'handleSend' in its own useCallback() Hook                                                                                                 react-hooks/exhaustive-deps
  1937:9   warning  'openPeerChat' is assigned a value but never used                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1977:9   warning  'handlePeerKeyDown' is assigned a value but never used                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  2247:25  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

frontend/app/plaza/page.tsx
  602:21  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

✖ 25 problems (0 errors, 25 warnings)
```

退出码：`0`。

#### R1验收7 / 02-spec 6.5

目录：`backend/`。

```bash
python -m pytest -q
```

实际输出：

```text
........................................................................ [  3%]
........................................................................ [  6%]
........................................................................ [  9%]
........................................................................ [ 13%]
........................................................................ [ 16%]
........................................................................ [ 19%]
........................................................................ [ 23%]
........................................................................ [ 26%]
........................................................................ [ 29%]
........................................................................ [ 33%]
........................................................................ [ 36%]
........................................................................ [ 39%]
........................................................................ [ 43%]
........................................................................ [ 46%]
.......................................................................E [ 49%]
F....................................................................... [ 53%]
........................................................................ [ 56%]
........................................................................ [ 59%]
........................................................................ [ 63%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 73%]
........................................................................ [ 76%]
........................................................................ [ 79%]
...................................EEE.E................................ [ 83%]
........................................................................ [ 86%]
........................................................................ [ 89%]
........................................................................ [ 93%]
........................................................................ [ 96%]
........................................................................ [ 99%]
....                                                                     [100%]
==================================== ERRORS ====================================
_ ERROR at setup of test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive _

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10d75c830>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x10eaad6a0>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python标准库>/socketserver.py:478: PermissionError
_____ ERROR at setup of test_drip_response_obeys_total_wall_clock_deadline _____

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10dc8ea50>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x10f582350>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python标准库>/socketserver.py:478: PermissionError
_________ ERROR at setup of test_fast_response_and_redirect_still_work _________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10dc8f4d0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x10f64b610>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python标准库>/socketserver.py:478: PermissionError
______ ERROR at setup of test_drip_headers_obey_total_wall_clock_deadline ______

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10d6e57f0>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x10f62ac40>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python标准库>/socketserver.py:478: PermissionError
___ ERROR at setup of test_four_stuck_resolutions_do_not_block_another_fetch ___

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10d2fc050>

    @pytest.fixture
    def local_fetch_server(monkeypatch):
>       server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_safe_http_deadline.py:51: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
<Python标准库>/socketserver.py:457: in __init__
    self.server_bind()
<Python标准库>/http/server.py:148: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <http.server.ThreadingHTTPServer object at 0x10f629810>

    def server_bind(self):
        """Called by constructor to bind the socket.
    
        May be overridden.
    
        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Since Linux 6.12.9, SO_REUSEPORT is not allowed
        # on other address families than AF_INET/AF_INET6.
        if (
            self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT")
            and self.address_family in (socket.AF_INET, socket.AF_INET6)
        ):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

<Python标准库>/socketserver.py:478: PermissionError
=================================== FAILURES ===================================
_________ test_stop_disconnects_async_upstream_and_releases_user_slot __________

client = <starlette.testclient.TestClient object at 0x10ea2d040>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x10d75c4b0>

    def test_stop_disconnects_async_upstream_and_releases_user_slot(client, monkeypatch):
        import services.exchange_service as service
    
        async def start_server():
            entered, disconnected = asyncio.Event(), asyncio.Event()
    
            async def handler(reader, writer):
                try:
                    headers = await reader.readuntil(b"\r\n\r\n")
                    length = 0
                    for line in headers.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            length = int(line.split(b":", 1)[1].strip())
                    if length:
                        await reader.readexactly(length)
                    entered.set()
                    await reader.read(1)
                    disconnected.set()
                finally:
                    writer.close()
                    await writer.wait_closed()
    
            server = await asyncio.start_server(handler, "127.0.0.1", 0)
            return server, entered, disconnected
    
        async def wait_event(event):
            await asyncio.wait_for(event.wait(), timeout=5)
    
>       server, entered, disconnected = client.portal.call(start_server)
                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_exchange_isolation.py:151: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv/lib/python3.14/site-packages/anyio/from_thread.py:338: in call
    return cast(T_Retval, self.start_task_soon(func, *args).result())
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python标准库>/concurrent/futures/_base.py:454: in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
<Python标准库>/concurrent/futures/_base.py:396: in __get_result
    raise self._exception
.venv/lib/python3.14/site-packages/anyio/from_thread.py:263: in _call_func
    retval = await retval_or_awaitable
             ^^^^^^^^^^^^^^^^^^^^^^^^^
tests/test_exchange_isolation.py:145: in start_server
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<Python标准库>/asyncio/streams.py:84: in start_server
    return await loop.create_server(factory, host, port, **kwds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <_UnixSelectorEventLoop running=True closed=False debug=False>
protocol_factory = <function start_server.<locals>.factory at 0x10f400eb0>
host = '127.0.0.1', port = 0, family = <AddressFamily.AF_UNSPEC: 0>
flags = <AddressInfo.AI_PASSIVE: 1>
sock = <socket.socket [closed] fd=-1, family=2, type=1, proto=6>, backlog = 100
ssl = None, reuse_address = True, reuse_port = None, keep_alive = None
ssl_handshake_timeout = None, ssl_shutdown_timeout = None, start_serving = True

    async def create_server(
            self, protocol_factory, host=None, port=None,
            *,
            family=socket.AF_UNSPEC,
            flags=socket.AI_PASSIVE,
            sock=None,
            backlog=100,
            ssl=None,
            reuse_address=None,
            reuse_port=None,
            keep_alive=None,
            ssl_handshake_timeout=None,
            ssl_shutdown_timeout=None,
            start_serving=True):
        """Create a TCP server.
    
        The host parameter can be a string, in that case the TCP server is
        bound to host and port.
    
        The host parameter can also be a sequence of strings and in that
        case the TCP server is bound to all hosts of the sequence.  If
        a host appears multiple times (possibly indirectly e.g. when
        hostnames resolve to the same IP address), the server is only bound
        once to that host.
    
        Return a Server object which can be used to stop the service.
    
        This method is a coroutine.
        """
        if isinstance(ssl, bool):
            raise TypeError('ssl argument must be an SSLContext or None')
    
        if ssl_handshake_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_handshake_timeout is only meaningful with ssl')
    
        if ssl_shutdown_timeout is not None and ssl is None:
            raise ValueError(
                'ssl_shutdown_timeout is only meaningful with ssl')
    
        if sock is not None:
            _check_ssl_socket(sock)
    
        if host is not None or port is not None:
            if sock is not None:
                raise ValueError(
                    'host/port and sock can not be specified at the same time')
    
            if reuse_address is None:
                reuse_address = os.name == "posix" and sys.platform != "cygwin"
            sockets = []
            if host == '':
                hosts = [None]
            elif (isinstance(host, str) or
                  not isinstance(host, collections.abc.Iterable)):
                hosts = [host]
            else:
                hosts = host
    
            fs = [self._create_server_getaddrinfo(host, port, family=family,
                                                  flags=flags)
                  for host in hosts]
            infos = await tasks.gather(*fs)
            infos = set(itertools.chain.from_iterable(infos))
    
            completed = False
            try:
                for res in infos:
                    af, socktype, proto, canonname, sa = res
                    try:
                        sock = socket.socket(af, socktype, proto)
                    except socket.error:
                        # Assume it's a bad family/type/protocol combination.
                        if self._debug:
                            logger.warning('create_server() failed to create '
                                           'socket.socket(%r, %r, %r)',
                                           af, socktype, proto, exc_info=True)
                        continue
                    sockets.append(sock)
                    if reuse_address:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                    # Since Linux 6.12.9, SO_REUSEPORT is not allowed
                    # on other address families than AF_INET/AF_INET6.
                    if reuse_port and af in (socket.AF_INET, socket.AF_INET6):
                        _set_reuseport(sock)
                    if keep_alive:
                        sock.setsockopt(
                            socket.SOL_SOCKET, socket.SO_KEEPALIVE, True)
                    # Disable IPv4/IPv6 dual stack support (enabled by
                    # default on Linux) which makes a single socket
                    # listen on both address families.
                    if (_HAS_IPv6 and
                            af == socket.AF_INET6 and
                            hasattr(socket, 'IPPROTO_IPV6')):
                        sock.setsockopt(socket.IPPROTO_IPV6,
                                        socket.IPV6_V6ONLY,
                                        True)
                    try:
                        sock.bind(sa)
                    except OSError as err:
                        msg = ('error while attempting '
                               'to bind on address %r: %s'
                               % (sa, str(err).lower()))
                        if err.errno == errno.EADDRNOTAVAIL:
                            # Assume the family is not enabled (bpo-30945)
                            sockets.pop()
                            sock.close()
                            if self._debug:
                                logger.warning(msg)
                            continue
>                       raise OSError(err.errno, msg) from None
E                       PermissionError: [Errno 1] error while attempting to bind on address ('127.0.0.1', 0): [errno 1] operation not permitted

<Python标准库>/asyncio/base_events.py:1637: PermissionError
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/fastapi/testclient.py:1
  backend/.venv/lib/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

.venv/lib/python3.14/site-packages/slowapi/extension.py:720: 2 warnings
tests/test_account_deletion.py: 8 warnings
  backend/.venv/lib/python3.14/site-packages/slowapi/extension.py:720: DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated and slated for removal in Python 3.16; use inspect.iscoroutinefunction() instead
    if asyncio.iscoroutinefunction(func):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
ERROR tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
ERROR tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
ERROR tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
ERROR tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch
1 failed, 2158 passed, 11 warnings, 5 errors in 56.72s
```

退出码：`1`。

预期总数为 `2052 + 112 = 2164`。本次 `2158 passed + 1 failed + 5 errors = 2164`；六个未通过节点与首轮报告及未修改基线复现完全相同，均在回环端口 bind 阶段遭 EPERM。返修规格第 7 条允许忽略沙箱内这六项，完整通过仍需沙箱外重跑确认。

### 原 02-spec 保护与外链验收复跑

#### 02-spec 6.2

目录：`仓库根目录`。

```bash
git diff --exit-code -- backend/tests/test_card_detail.py backend/tests/test_beijing_time.py backend/tools/card_detail.py backend/tools/topic_expand.py backend/tools/visual_search.py backend/utils/safe_http.py
```

实际输出：无输出。

退出码：`0`。

#### 02-spec 6.3

目录：`仓库根目录`。

```bash
git diff -U0 -- backend/tools/web_search.py | grep -n '_search_weather_direct'
```

实际输出：无输出。

退出码：`1`。

#### 02-spec 6.4

目录：`仓库根目录`。

```bash
grep -n "_get_client" backend/tools/web_search.py backend/tools/travel_plan.py
```

实际输出：无输出。

退出码：`1`。

#### 02-spec 6.8a

目录：`frontend/`。

```bash
grep -n "toSafeExternalUrl" components/ChatBubble.tsx lib/open.ts
```

实际输出：

```text
components/ChatBubble.tsx:9:import { openExternal, toSafeExternalUrl } from "@/lib/open";
components/ChatBubble.tsx:249:            const url = toSafeExternalUrl(source.url);
lib/open.ts:30:export function toSafeExternalUrl(url: unknown): string | null {
```

退出码：`0`。

#### 02-spec 6.8b

目录：`frontend/`。

```bash
grep -n "openExternal" components/ChatBubble.tsx
```

实际输出：

```text
9:import { openExternal, toSafeExternalUrl } from "@/lib/open";
289:                        onClick={() => void openExternal(url)}
```

退出码：`0`。

### 本轮范围与追加方式复核

实际输出：

```text
All changed paths are within the specification allowlist
Existing authorized test edits, other frontend files, specifications, and review preserved
Original 72 source-test cases preserved byte-for-byte; R1 tests appended
Existing report preserved byte-for-byte
Both date directive functions preserved
Weather dispatch preserved byte-for-byte
No new repository files added during R1
```

退出码：`0`。

`git diff --check`：无输出，退出码 `0`。追加前确认既有报告为 40722 字节、SHA-256 `30060eefb4d517afe031c348df9562f5aa930fc1bbf796f852e762e8b4c89d34`；本节采用文件末尾追加，前文不重写。

### 全库文档扫描与人工项

全库检索覆盖 30 秒、socket 超时、两项 DashScope 超时/重试环境变量、重试、热点分类和 qwen-plus；核对了代码和所有现行 Markdown 陈述点。五份允许文档已写全四项原生调用的例外。历史任务、原报告前文、02 / 04 / 05 文档和截图均保持原样，既有报告中的首轮说明作为历史记录保留；本节与五份现行文档记录 R1 后的准确范围。白名单外 `backend/.env.example` 的既有默认客户端注释未修改，当前配置例外由 README 和部署手册明确说明。

- R1-1–R1-4 实现没有未完成项。返修验收第 5 条原文的扫描范围会自匹配规格和新增日志，需要确认以排除任务记录后的现行文档为核对范围；本轮已给出实际命中与现行文档无匹配证据，没有修改规格消除命中。
- 由 Claude 在沙箱外重跑后端全量 `python -m pytest -q`，预期全部 2164 个用例通过。本轮沙箱内六处既有端口权限异常按返修第 7 条处理，未改动受保护测试或绕过沙箱。
- 本轮没有运行 npm build/dev、启动后端服务或尝试真实网络请求。R1 的正文去 URL 行为、来源标题异常值与箭头 hover 颜色可在沙箱外补充真实接口/界面复核；04-review 的构建、接口和截图结论是首轮验收记录。
- 卡片与来源仍不落库，刷新或切换会话后来源不保留，是原规格明确保留的限制。
