from enterprise_rag_mvp.models import PolicyChunk


def sample_policy_chunks() -> list[PolicyChunk]:
    return [
        PolicyChunk(
            chunk_id="leave-annual-001",
            doc_id="employee-leave-policy",
            block_id="article-3",
            text=(
                "2. 带薪年假（适用于全体非教学老师） "
                "2.1 按照员工的本单位连续工龄，年休假天数如下："
                "第一年 第二年 第三年 第四年 第五年 第六年及以后 "
                "10天 12天 14天 16天 18天 20天。"
                "2.1年休假不包括法定节假日及周末公休日；"
                "2.2非教学老师使用年休假规则：非寒暑假时间（学期内）单次请假原则上不能连续超过5天；"
                "2.3如员工未能在某一个入职年度里休完年休假，学校允许员工在该入职年度结束后的3个月内休完。"
            ),
            heading_path=["员工休假管理办法", "第三条 年休假"],
            metadata={"source": "员工休假管理办法.md", "page": 3, "policy_type": "leave", "source_url": "https://example.com/policyDetail/3"},
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
            heading_path=["***公司人守则-工作时间及假期管理制度", "旷工处理"],
            metadata={"source": "工作时间及假期管理制度.md", "page": 11, "policy_type": "attendance", "source_url": "https://example.com/policyDetail/11"},
        ),
        PolicyChunk(
            chunk_id="discipline-absence-classification-001",
            doc_id="employee-discipline-policy",
            block_id="class-2-management-order",
            text=(
                "（二）二类违规行为 二类违规行为：指违反师德师风、学校保密义务、"
                "破坏学校管理秩序等致使学校经济、形象、声誉遭受严重损害的行为。"
                "5. 破坏学校管理秩序行为 5.1渎职给学校造成较大损失。5.2旷工少于三天。"
            ),
            heading_path=["***公司人守则-员工纪律制度", "二类违规行为", "破坏学校管理秩序行为"],
            metadata={"source": "员工纪律制度.md", "page": 16, "policy_type": "conduct", "source_url": "https://example.com/policyDetail/16"},
        ),
        PolicyChunk(
            chunk_id="discipline-category-2-children-001",
            doc_id="employee-discipline-policy",
            block_id="class-2-children",
            text=(
                "二类违规行为\n"
                "1. 师德师风相关的违规行为\n"
                "2. 违反保密义务行为\n"
                "3. 侵犯学校权益行为\n"
                "4. 弄虚作假行为\n"
                "5. 破坏学校管理秩序行为"
            ),
            heading_path=["***公司人守则-员工纪律制度", "二类违规行为"],
            metadata={
                "source": "员工纪律制度.md",
                "page": 16,
                "policy_type": "conduct",
                "source_url": "https://example.com/policyDetail/16",
                "chunk_type": "section_children",
                "chunking_strategy": "policy_structure",
                "node_type": "violation_level",
                "section_title": "二类违规行为",
                "child_count": 5,
                "ordinal_sequence": ["1.", "2.", "3.", "4.", "5."],
                "ordinal_continuity_status": "complete",
            },
        ),
        PolicyChunk(
            chunk_id="discipline-absence-severe-classification-001",
            doc_id="employee-discipline-policy",
            block_id="class-1-management-order",
            text=(
                "（一）一类违规行为 一类违规行为：指性质严重、影响恶劣的违规行为。"
                "5. 破坏学校管理秩序行为 连续旷工3个工作日及以上，"
                "或一年内累计两次及以上旷工，属于一类违规行为中的破坏学校管理秩序行为。"
            ),
            heading_path=["***公司人守则-员工纪律制度", "一类违规行为", "破坏学校管理秩序行为"],
            metadata={"source": "员工纪律制度.md", "page": 16, "policy_type": "conduct", "source_url": "https://example.com/policyDetail/16"},
        ),
        PolicyChunk(
            chunk_id="discipline-lateness-classification-001",
            doc_id="employee-discipline-policy",
            block_id="class-3-management-order-lateness",
            text=(
                "（三）三类违规行为 三类违规行为：指一般的违规行为。"
                "5. 破坏学校管理秩序行为 5.1一学年中出现两次及两次以上迟到、早退、随意停课、私自找人顶课或调课等。"
            ),
            heading_path=["***公司人守则-员工纪律制度", "三类违规行为", "破坏学校管理秩序行为"],
            metadata={"source": "员工纪律制度.md", "page": 16, "policy_type": "conduct", "source_url": "https://example.com/policyDetail/16"},
        ),
        PolicyChunk(
            chunk_id="discipline-language-classification-001",
            doc_id="employee-discipline-policy",
            block_id="class-3-rights-language",
            text=(
                "（三）三类违规行为 三类违规行为：指一般的违规行为。"
                "4. 侵犯学校权益行为 4.1未经许可将学校资产主要用作私人用途。"
                "4.2对客户、来访者怠慢或语言不得体，并引起投诉。"
            ),
            heading_path=["***公司人守则-员工纪律制度", "三类违规行为", "侵犯学校权益行为"],
            metadata={"source": "员工纪律制度.md", "page": 16, "policy_type": "conduct", "source_url": "https://example.com/policyDetail/16"},
        ),
        PolicyChunk(
            chunk_id="discipline-teacher-ethics-classification-001",
            doc_id="employee-discipline-policy",
            block_id="class-2-teacher-ethics",
            text=(
                "（二）二类违规行为 二类违规行为：指违反师德师风、学校保密义务、"
                "破坏学校管理秩序等致使学校经济、形象、声誉遭受严重损害的行为。"
                "1. 师德师风相关的违规行为 1.1违反教师职业行为准则中的限制性规定，"
                "如未按规定履行教育教学职责、未维护学生合法权益等。"
            ),
            heading_path=["***公司人守则-员工纪律制度", "二类违规行为", "师德师风相关的违规行为"],
            metadata={"source": "员工纪律制度.md", "page": 16, "policy_type": "conduct", "source_url": "https://example.com/policyDetail/16"},
        ),
        PolicyChunk(
            chunk_id="discipline-salary-classification-001",
            doc_id="employee-discipline-policy",
            block_id="class-2-confidentiality-salary",
            text=(
                "（二）二类违规行为 2. 违反保密义务行为 "
                "2.1非因工作需要获取、使用、泄露、传播保密信息。"
                "2.2其他违反数据安全规范等制度。"
                "2.3打听、讨论员工工资、奖金、津贴补贴等个人待遇信息。"
            ),
            heading_path=["***公司人守则-员工纪律制度", "二类违规行为", "违反保密义务行为"],
            metadata={"source": "员工纪律制度.md", "page": 16, "policy_type": "conduct", "source_url": "https://example.com/policyDetail/16"},
        ),
        PolicyChunk(
            chunk_id="discipline-false-reimbursement-classification-001",
            doc_id="employee-discipline-policy",
            block_id="class-2-falsification-reimbursement",
            text=(
                "（二）二类违规行为 4. 弄虚作假行为 "
                "4.1向学校隐瞒或有意提交虚假的重大信息。"
                "4.2在老师个人及学生各级考试各类评选活动中弄虚作假。"
                "4.3虚假报销，例如报销未发生的费用或以虚假理由报销费用等。"
                "4.4其他弄虚作假给学校造成严重不良影响或经济、声誉损失的行为。"
            ),
            heading_path=["***公司人守则-员工纪律制度", "二类违规行为", "弄虚作假行为"],
            metadata={"source": "员工纪律制度.md", "page": 16, "policy_type": "conduct", "source_url": "https://example.com/policyDetail/16"},
        ),
        PolicyChunk(
            chunk_id="discipline-violation-actions-001",
            doc_id="employee-discipline-policy",
            block_id="violation-actions",
            text=(
                "五、违规行为相应处理 1.1一类违规行为：处分生效当年年度绩效为低于期望，并解除劳动合同。"
                "1.2二类违规行为：予以记过处分，自处分生效日起一年内不得调薪并取消当年年终奖激励资格。"
                "1.3三类违规行为：予以书面或口头警告。"
            ),
            heading_path=["***公司人守则-员工纪律制度", "违规行为相应处理"],
            metadata={"source": "员工纪律制度.md", "page": 16, "policy_type": "conduct", "source_url": "https://example.com/policyDetail/16"},
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
