# QQOVO 认证协议调查

调查日期：2026-11-06。仅调查，未修改 Music Core 或其他项目源码，未提交Git。按用户要求，下载的公开main分支源码快照位于 `C:/Code_Home/2_projects/media-lab/references/openmusic-main` 和 `C:/Code_Home/2_projects/media-lab/references/Meting-API-main`。以下行号以本次本地快照为准；ZIP没有Git提交元数据，不能作为线上版本证明。公开仓库：[OpenMusic](https://github.com/qq01-hub/openmusic)、[Meting-API](https://github.com/qq01-hub/Meting-API)。

## 结论

**不只是登录门槛发生差异，当前公开主链已不再向客户端下发旧apiSignKey。** 旧客户端期待匿名Bootstrap返回签名材料；当前公开实现即使走成功分支也只返回clientId/features。旧HMAC实现仍残留在apiSign.js，但未发现其导出函数被当前运行主链引用。因此“正常登录后继续取apiSignKey”也不是这份公开源码所支持的完整适配方案。

线上匿名Bootstrap确实返回loginRequired，但无法确认qqovo.top运行的就是本次公开main快照；不能由线上一个响应推定全部实现，更不能断言旧musicdl历史上的成功必定来自qqovo。

## 1. 旧客户端：源码已证实

冻结版 `C:/Code_Home/2_projects/media-lab/references/musicdl-master/musicdl/modules/sources/qq.py:365` `_parsewithqqovoapi`：

1. 从搜索结果mid/songmid取稳定ID；必要时_getsongmetainfo补展示元数据。
2. 372行创建全新requests.Session和UUID deviceId；373行POST /api/session/bootstrap，JSON只含deviceId，带Origin/Referer/普通UA。没有OpenMusic登录操作，没有预先载入账号Session；Session接收Set-Cookie并用于后续请求。
3. 374行取顶层apiSignKey，缺失时默认空字符串，没有检查authenticated/loginRequired。
4. 369行构造签名：GET、path、按键排序的解码query、空body摘要、秒时间戳、UUID nonce，以换行连接；HMAC-SHA256，Base64URL无padding；通过X-OM-Ts/Nonce/Sign发送。
5. 376–378行GET /api/meting，server=tencent、type=url、id=MID、quality=lossless，解析url并交audio_link_tester探测媒体；不自行解密音频。
6. 386–397行_parsewiththirdpartapis把qqovo列为L2第二项；外层抑制各路线异常，成功立即停止。因此编排最终成功不能单独证明qqovo成功。

旧Lab此前成功编排及新Core记录见新工程docs/migration/39-B-4D-4、39-B-4D-5。新Core `server/app/providers/qq_resolvers/qqovo.py:23` 同样新建短生命周期AsyncClient，Bootstrap缺key明确停止，避免旧版继续用空key请求；HMAC函数在15行。签名算法的基本组成与旧版相同，当前失败发生在取得签名材料之前，不是证明HMAC计算错误。

## 2. OpenMusic当前主链：源码已证实

下列位置均相对于本地 `references/openmusic-main/`；可与[公开index.js](https://github.com/qq01-hub/openmusic/blob/main/server/index.js)对照。

| 文件/行号/函数 | 作用 |
|---|---|
| server/index.js:2623，POST /api/session/bootstrap | 限流，resolveAccountFromRequest，账号/身份/设备恢复或新建 |
| server/index.js:2600，sendBootstrapResponse | 先设身份Cookie；2604行仅在`!res.req.account && !runtime.anonymousLoginEnabled`时返回authenticated=false/loginRequired=true；2605–2615行成功payload没有apiSignKey |
| server/index.js:2315，resolveAccountFromRequest | 从账户Session Token检查账户；无token返回null |
| server/index.js:2635–2645 | 有合法账户时取得roomUserId，绑定设备到用户，并签发/续期房间身份Cookie |
| server/index.js:2652–2691 | 既有身份Cookie、服务端device Cookie恢复或创建新身份；body deviceId不是账户登录证明，也不允许任意恢复另一用户 |
| server/index.js:2109–2111、2197–2202 | openmusic_uid/openmusic_token/openmusic_did身份及设备Cookie |
| server/index.js:2223–2230，setAccountSessionCookie | 账户access/refresh会话Cookie独立于上述房间身份；refresh限/api/auth，HttpOnly |
| server/index.js:603–616 | 挂载createAccountRequestGuard、createAccountAccessMiddleware及设备校验、账户风险上下文 |
| server/accountAccess.js:54–90，createAccountAccessMiddleware | 保护API时解析账户或允许的匿名账户；无账户401 ACCOUNT_AUTH_REQUIRED；音乐访问对非匿名账户执行verifyDevice；核对房间身份与账户 |
| server/index.js:1803–1849，GET /api/meting | 普通媒体要求requireSessionIdentity，检查音源开关，在用户/房间上下文中proxyMetingResponse；公开封面例外不等于媒体匿名可用 |
| server/index.js:2944，POST /api/auth/email/login | 正常邮箱登录入口；另有注册、LinuxDo/GitHub OAuth和微信账户流程，实际可用性取决于站点配置 |

**apiSignKey来源：** `server/apiSign.js:98` deriveApiSignKey使用服务端clientIdSecret，对`om-api-sign:userId:iat`作HMAC-SHA256，生成Base64URL字符串；这是OpenMusic请求签名材料，不是QQ会员凭据、QQ vkey或音频解密密钥。该文件176行verifyApiSign验证头/查询签名、时间窗、nonce、body哈希及恒定时间比较。媒体GET不消费nonce的旧设计也在该文件中。

但全仓JS/TS引用检索只找到这些函数自身定义，未找到当前index.js导入/调用；当前Bootstrap也不返回key。故这些代码只能证明旧签名方案的实现，**不能宣称当前/api/meting仍必经该验证器**。当前实际接入的账户和设备中间件才是本快照主链。有关旧版本何时下发key、具体哪次提交删除，尚无提交历史直接证据。

## 3. OpenMusic到Meting，与平台权限的关系

源码位置相对于两个参考快照：

- OpenMusic `server/metingUpstream.js:269–271` buildMetingAuthHeaders：服务端Bearer令牌配合createMetingAssertion；`server/metingAssertion.js:1–16`生成X-OpenMusic-Assertion/Signature。这是**服务端到服务端**授权，不是旧浏览器X-OM签名。
- `server/metingUpstream.js:275–300` 对受房间范围控制的请求转/admin/openmusic，使用管理配置的API Token，并可带房间作用域X-OpenMusic-Cookie。不能据此认为任意用户能取到共享账号Cookie。
- Meting-API `app.js:39` 把/api挂到apiTokenMiddleware；`src/middleware/auth.js:16–59` apiTokenMiddleware只接受Bearer API Token，调用store.validateApiToken；开启OpenMusic认证时另检查并验证服务断言。
- Meting-API `src/middleware/openmusicAssertion.js:16–38` verifyMetingAssertion检查签名、时间、nonce和防重放，返回accountId/purpose。与客户端deviceId、旧apiSignKey均不同。
- Meting-API `src/service/api.js:32–75`：显式X-OpenMusic-Cookie优先，否则从管理员维护的Cookie池按平台及品质挑可用账号；url请求没有可用账号则503 MUSIC_ACCOUNT_UNAVAILABLE。103行等把选定Cookie传入平台Provider，存在有限账号失败切换。`src/providers/tencent/song.js:126–198`使用QQ GetVkey等平台请求取得purl/媒体地址，仍受账号及平台返回结果约束。

三者应严格分开：OpenMusic账户决定能否进入服务；平台账号及实际会员权限决定上游允许的媒体；API Token/断言或旧HMAC验证调用者和请求。**拥有OpenMusic登录不等于拥有QQ会员，拿到签名材料也不能赋予会员资格。** 源码表明凭据来源是配置账号池/房间作用域账号，不证明线上具体账号归属、资源下载授权或用户已获相应许可；本期未登录、读取或提取任何此类凭据。

## 4. 线上实际请求与证据分级

本次仅一次全新匿名会话POST https://qqovo.top/api/session/bootstrap，随机UUID deviceId、同站Origin/Referer：HTTP200；authenticated=false、loginRequired=true、apiSignKeyPresent=false。设置了身份/设备Cookie（仅记录名称，未保存值）。没有继续请求受保护/api/meting。

- **实际请求已证实：** 当前匿名请求缺签名材料且被提示登录；发身份Cookie并不等于已登录账户。
- **源码已证实：** 本快照loginRequired分支是无account且禁用anonymousLoginEnabled；成功分支也无apiSignKey；主链账户/设备访问控制已代替旧客户端所期待的交互。
- **合理推测：** 若线上使用相同分支，匿名访问关闭且本次没有合法账户Session就是此次提示的原因；旧musicdl匿名取key预期对应更早部署行为。
- **尚未确认：** qqovo.top部署commit、是否有私有补丁、线上正常登录后的响应及设备证明细节、旧qqovo具名历史成功和匿名行为变化日期。仓库About链接qqovo.top只能证明项目关联，不能证明版本一致。未进行任何登录绕过或伪造会话。

## 5. 最小兼容建议（仅建议，未实施）

1. 继续保持qqovo暂不参与正常解析；不要把关闭新Core缺key判断作为修复，因为旧版空key签名也不解决账户访问控制。
2. 先由服务运营者确认线上版本及受支持的程序化调用方式。若仍使用旧协议，确认正常授权Session下是否确实下发apiSignKey，再适配同Session的Bootstrap/签名；不要预设登录一定能得到key。
3. 若对应当前公开版本，应适配其正常账户、设备绑定及获准的服务接口，而非强行继续旧Bootstrap-HMAC。账户、房间身份和设备Cookie须保持一致；随机UUID本身不能代替登录或设备证明。当前Core每次销毁短会话，不适合未经设计就复用长期登录，需另一期明确授权范围后做最小接入。
4. 由运营方明确授权的自部署Meting调用，应按其Bearer/断言和合法平台账号配置使用；不能把服务端令牌塞进浏览器，也不从他人部署提取令牌。此方案不是本次自动迁移目标。

本期只新增此报告及用户指定references中的公开源码快照，未修改任何项目源码或解析顺序，也未运行不相关回归测试。
