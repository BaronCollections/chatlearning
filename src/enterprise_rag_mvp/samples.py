from enterprise_rag_mvp.models import PolicyChunk


def sample_policy_chunks() -> list[PolicyChunk]:
    return [
        PolicyChunk(
            chunk_id="leave-annual-001",
            doc_id="employee-leave-policy",
            block_id="article-3",
            text="员工连续工作满一年后，可依法享受带薪年休假。年休假天数根据累计工作年限确定。",
            heading_path=["员工休假管理办法", "第三条 年休假"],
            metadata={"source": "员工休假管理办法.md", "page": 3, "policy_type": "leave"},
        ),
        PolicyChunk(
            chunk_id="attendance-late-001",
            doc_id="attendance-policy",
            block_id="article-5",
            text="员工迟到、早退应按考勤制度处理。月度多次迟到可能影响绩效考核。",
            heading_path=["考勤管理制度", "第五条 迟到早退"],
            metadata={"source": "考勤管理制度.md", "page": 5, "policy_type": "attendance"},
        ),
        PolicyChunk(
            chunk_id="attendance-absence-penalty-001",
            doc_id="worktime-leave-policy",
            block_id="absenteeism-penalty",
            text=(
                "（三）旷工 凡符合以下情况之一的应视为旷工。"
                "连续旷工3个工作日以下的，扣除旷工期间工资，并给予记过处分；"
                "连续旷工3个工作日及以上的，或一年内累计两次及以上旷工的，扣除旷工期间工资，并给予辞退处分。"
            ),
            heading_path=["云谷人守则-工作时间及假期管理制度", "旷工处理"],
            metadata={"source": "工作时间及假期管理制度.md", "page": 11, "policy_type": "attendance", "source_url": "https://work.yungu.org/policyDetail/11"},
        ),
        PolicyChunk(
            chunk_id="discipline-absence-classification-001",
            doc_id="employee-discipline-policy",
            block_id="class-2-management-order",
            text=(
                "（二）二类违规行为 二类违规行为：指违反师德师风、学校保密义务、"
                "破坏学校管理秩序等致使学校经济、形象、声誉遭受严重损害的行为。"
                "4. 破坏学校管理秩序行为 4.1渎职给学校造成较大损失。4.2旷工少于三天。"
            ),
            heading_path=["云谷人守则-员工纪律制度", "二类违规行为", "破坏学校管理秩序行为"],
            metadata={"source": "员工纪律制度.md", "page": 16, "policy_type": "conduct", "source_url": "https://work.yungu.org/policyDetail/16"},
        ),
        PolicyChunk(
            chunk_id="expense-travel-001",
            doc_id="expense-policy",
            block_id="article-8",
            text="员工差旅报销应提交真实有效票据，并在出差结束后按公司流程发起报销申请。",
            heading_path=["费用报销制度", "第八条 差旅报销"],
            metadata={"source": "费用报销制度.md", "page": 8, "policy_type": "expense"},
        ),
        PolicyChunk(
            chunk_id="security-data-001",
            doc_id="information-security-policy",
            block_id="article-4",
            text="员工不得将公司内部资料、客户数据或账号凭证通过个人网盘、私人邮箱等方式外传。",
            heading_path=["信息安全管理规范", "第四条 数据外传"],
            metadata={"source": "信息安全管理规范.md", "page": 4, "policy_type": "security"},
        ),
    ]
