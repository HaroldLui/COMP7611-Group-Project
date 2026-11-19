# Commit hash map (history rewrite, 2026-11-19)

On 2026-11-19 the repository history was rewritten to normalise commit authorship and remove
tool-generated commit-message trailers. **File contents did not change**: every rewritten commit has
exactly the same tree as the original. Only commit hashes changed.

Run records (`results/*/run_args.json`, `manifest.json`, checkpoints) and earlier documents quote
the original hashes. They are kept as recorded. Use this table to translate them, e.g. the frozen
code commit `3df873e` is now `a76854a`, and the results snapshot `dbaa629` is now `477fb6c`.

| date | original | rewritten | subject |
|---|---|---|---|
| 2026-10-28 | `4502e1e` | `52816a6` | Add DeepSeek v3 dev pilot and G2 probe with the new payloads |
| 2026-10-28 | `6846779` | `f9dc959` | Merge pull request #1 from HaroldLui/pilot-deepseek-g1-split |
| 2026-10-28 | `c4721d4` | `d90098e` | Merge pull request #2 from HaroldLui/pilot-deepseek-g1-split |
| 2026-10-28 | `3c134b0` | `9e7644d` | Multi-agent prompt-injection study: harness, scenarios, analysis, paper skeleton |
| 2026-10-28 | `b10af33` | `df3b470` | Realistic injection payloads, company-domain markers, more pilot results |
| 2026-10-28 | `92f2aff` | `1842ae7` | Split G1 scoring and add DeepSeek v4.1-flash dev pilot |
| 2026-10-29 | `fc44392` | `0eaca15` | Extend dev pilot to all five configs (M3/M4) + comprehensive dev-pilot report |
| 2026-10-29 | `4c8bdde` | `594e79a` | Freeze the preregistration; record the schema-fix re-run outcome |
| 2026-10-29 | `9fdaa41` | `8476d9a` | M2/M4 dev re-run with schema fix |
| 2026-10-29 | `08458af` | `3c372b7` | Merge pull request #3 from HaroldLui/review-fixes |
| 2026-10-29 | `3985ac1` | `20d0cff` | Merge pull request #4 from HaroldLui/pilot-deepseek-g1-split |
| 2026-10-29 | `2a559ae` | `43aa903` | Merge pull request #5 from HaroldLui/review-fixes |
| 2026-10-29 | `3df873e` | `a76854a` | Report missing metrics as n/a, record run provenance, tighten detection wording |
| 2026-10-29 | `5852ed5` | `5960afa` | Review fixes: visible schema constraints, requester notices, detection metric, report corrections |
| 2026-10-29 | `5627d1e` | `4f348e6` | docs: add ver6 project outline and qualify post-fix pilot conclusions |
| 2026-11-01 | `f061486` | `77b7c2d` | Merge pull request #6 from HaroldLui/freeze-prereg |
| 2026-11-02 | `400cdf3` | `c19ac46` | Add GLM gateway pilot and reproducible test entry point |
| 2026-11-02 | `5585c12` | `5c3348e` | Add gateway test-split results for H4 (DeepSeek v4.1-flash, 1,350 episodes) |
| 2026-11-02 | `fa8a000` | `dfe0bbb` | Add main test-split results (DeepSeek v4.1-flash, 2,700 episodes) |
| 2026-11-02 | `ed0faa7` | `11e0d46` | Add presentation demo that replays recorded test-split episodes |
| 2026-11-02 | `615c2b8` | `ee6f143` | Merge pull request #7 from HaroldLui/test-deepseek-results |
| 2026-11-02 | `1b59062` | `2bc6732` | Merge pull request #8 from HaroldLui/test-deepseek-gateway |
| 2026-11-02 | `26ceac6` | `46baf24` | Merge pull request #9 from HaroldLui/demo-replay |
| 2026-11-13 | `de79ed4` | `452466d` | Add GLM-5.3 Aliyun test results and execution provenance |
| 2026-11-13 | `2cd0a05` | `20b83b4` | Merge pull request #10 from HaroldLui/results/glm-5.3-aliyun |
| 2026-11-14 | `9992c58` | `a5535a8` | Add 9-page report draft (paper/report.tex) |
| 2026-11-14 | `8c05701` | `e4730d8` | Add Qwen3.8-flash Aliyun test results and failure review |
| 2026-11-14 | `c86da91` | `8ebc4cc` | Add cross-model comparison and report section (DeepSeek, GLM-5.3, Qwen3.8) |
| 2026-11-14 | `782c6b8` | `70f5a53` | Add model logos under the x axis of the cross-model figure |
| 2026-11-14 | `1847802` | `3ad1c9d` | Deepen the report: factorial effects, stage-wise propagation, single typeface |
| 2026-11-14 | `dbaa629` | `477fb6c` | Merge pull request #11 from HaroldLui/results/qwen3.8-flash-aliyun |
| 2026-11-14 | `79f15f1` | `ecdf9ee` | Use the supplied GLM logo in the cross-model figure |
| 2026-11-19 | `f35550f` | `b27a9b0` | Adopt the team's revised report text with APA 7 citations and references |
| 2026-11-19 | `24465ea` | `2eb2c1b` | Rewrite report prose in a more natural voice; restore logo bar chart |

Full 40-character hashes:

```
4502e1ef3fb9354dd2b31a19cae1f45046ca689d 52816a6b8e3ae1c141fe96207b029234a4633325
68467791482240394443853a25d3f7ccb4db2205 f9dc959d975de02b5f021e9d07010e6bdb01ad1c
c4721d4bae35c9fc4d45a4f567c664e5b09857ea d90098e49c30e102122215b65bfc93c93e4d9502
3c134b09046bda75005e88745c77b7208f7117cf 9e7644ddcded98a217609e2264db473e0bc9e6c4
b10af3325b2a376270d58ddf8e1e98c760ace218 df3b4705a65aebfe47e85e987c59ce58fb0a4d7d
92f2aff1ddf7f08bbb22a4532e720d4174b746f4 1842ae772e8985b151f4bbc7849286ae49f62684
fc44392195778c85a29e4410608e7779b782e77b 0eaca15814941116ec22d78dd755519b8a8e5a7f
4c8bdde1da88af1aa68f2b3efebdfe97f2cd6cef 594e79a70511d66090224fa62e0be462c6586919
9fdaa41c7156a20a37ecaf31a288ab20073ba60c 8476d9afde3be8a134dbf353e81aec690e9c1de1
08458af02e9622e0f4322d329434db5121a9984c 3c372b75ae5a7c582df79878ba29edcbb889c88e
3985ac14a453a438b33e99bfbace44a8103b25fc 20d0cfff1979192de7077480ddabf96ad4299eae
2a559aeb17fcf7407e33daf37e9581c73bf0fb39 43aa903742e4b43b15cbe3c92d2b47f72e95eb2b
3df873efe114f138c7e5d3f9098382b46aa5559d a76854a87203845b29cff8569514af7e46161119
5852ed5fd10b2a9c75eb5891e51d15526bc40f69 5960afa59e9c50ffcda56b9aaa32f7d229b1f9bd
5627d1ee67348fa5b9ad773470f8d1eba9223861 4f348e6874fe403286d1f0df3939fc6f886373dc
f0614864826bcc00e8b057df6fb594925508801e 77b7c2dae2841977428b49bf737c9322d40109c8
400cdf30fa3b71f99a3732c5b6d7ede074fbb9de c19ac468619a1c5438344dc2b7c368adfa2f78db
5585c12eabf144cffc278d15a9c055b2d7494494 5c3348edbb0f560ac9321bd0ebe7518f47a05e08
fa8a000579999215a6cc603b02051757bc68416e dfe0bbb76d88414d0339eac5d2f1c60a0fe92f73
ed0faa7e78b729ff1202c56d4723d81282201723 11e0d46c034474aaffcbb5b1e69895fb511c8350
615c2b8a42297ac5685ecae3e084bb9fb0694262 ee6f143881e6ed00b2d7a95c93086cda1779dfc2
1b590624b79c6379a9cec20ff65d5df6d02298d9 2bc673261bbfdc97da696f7720ecd2a65cf7cfe6
26ceac62925311b6217603c3feac03d94d35e106 46baf2434e0b48db5c4bbe3196e770b7b9ea243d
de79ed41c15d2dfa2a5273d606def51d47cd5b3e 452466dbd17772ea3f3e47fba76b7839efda691b
2cd0a05c29eb4b7d458d0618a8789b1b4f9ed1a0 20b83b4808640ba84a0d0362e68fcde0071afdc9
9992c587ea4ed2187aa3f4dbf16bcb8028e084e4 a5535a8a3457509bcfdb66e8f2fcef33e3e63645
8c05701a238748e48a34607a72cb0af0f31ee259 e4730d84934336aa0d002b3677e5def7438bc5bf
c86da9195a0b7865083db7f24004325be000d18c 8ebc4cc36c577f02a40d76c97b59a2aeef796aa6
782c6b8498675b0080eeb7cd90242ad7a1f9b190 70f5a53ea18f42cae6b45fc36b5711a4a7343f62
18478027097f2d458deedd1def0d7c670dc89f6b 3ad1c9d216070d7ec6847050c60f284a7f443856
dbaa62949eef37b0d7e65e0cf823c31b132be54f 477fb6c2ac63e87c98a62bc7dde09bb8c5475357
79f15f1ad0e6c18e1c07eddb4c4d40db514bc34b ecdf9eee3b3dbc950a9d9ac8c95c10632543226b
f35550f7cd0db51b41c2460ac5f271ee60aa555a b27a9b03a4783591d0686cc32ff63a35e3ba6a2b
24465eab7a1c20a29d6ed62416ad91eee48c2590 2eb2c1bb995ec74658d3e4f7159bdba0846afa60
```
