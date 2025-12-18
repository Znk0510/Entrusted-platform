# routes/rating.py
from fastapi import APIRouter, Depends, HTTPException, Request, status, Form
from fastapi.responses import RedirectResponse
from typing import Optional

from db import getDB
from routes.auth import get_current_user

router = APIRouter(prefix="/api", tags=["rating"])


# ------------------------------------------------------
# ⭐ POST：提交評價（給你目前的前端用）
# ------------------------------------------------------
@router.post("/ratings")
async def create_rating(
    project_id: int = Form(...),
    ratee_id: int = Form(...),
    rating_direction: str = Form(...),

    overall_comment: str | None = Form(None),

    output_quality_score: int | None = Form(None),
    execution_efficiency_score: int | None = Form(None),
    contractor_attitude_score: int | None = Form(None),

    requirement_rationality_score: int | None = Form(None),
    acceptance_difficulty_score: int | None = Form(None),
    client_attitude_score: int | None = Form(None),

    conn=Depends(getDB),
    user: dict = Depends(get_current_user),
):
    async with conn.cursor() as cur:
        # 1️⃣ 專案檢查
        await cur.execute(
            "SELECT client_id, contractor_id, status FROM projects WHERE id = %s",
            (project_id,)
        )
        project = await cur.fetchone()

        if not project or project["status"] != "completed":
            raise HTTPException(status_code=400, detail="Project not completed")

        # 2️⃣ 防重複評價
        await cur.execute(
            """
            SELECT 1 FROM ratings
            WHERE project_id = %s AND rater_id = %s
            """,
            (project_id, user["id"])
        )
        if await cur.fetchone():
            raise HTTPException(status_code=400, detail="Already rated")

        # 3️⃣ 寫入評價
        await cur.execute(
            """
            INSERT INTO ratings (
                project_id, rater_id, ratee_id, rating_direction,
                overall_comment,
                output_quality_score, execution_efficiency_score, contractor_attitude_score,
                requirement_rationality_score, acceptance_difficulty_score, client_attitude_score
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                project_id,
                user["id"],
                ratee_id,
                rating_direction,
                overall_comment,
                output_quality_score,
                execution_efficiency_score,
                contractor_attitude_score,
                requirement_rationality_score,
                acceptance_difficulty_score,
                client_attitude_score,
            )
        )

    # 4️⃣ 依角色 redirect（這裡不再用 payload）
    if user["role"] == "client":
        redirect_url = f"/client/project/{project_id}"
        msg = "你已成功評價接案人"
    else:
        redirect_url = f"/contractor/project/{project_id}"
        msg = "你已成功評價委託人"

    return RedirectResponse(
        url=f"{redirect_url}?message={msg}",
        status_code=303
)

@router.get("/contractors/{contractor_id}/rating-preview")
async def get_contractor_rating_preview(
    contractor_id: int,
    conn=Depends(getDB)
):
    async with conn.cursor() as cur:
        # 平均評價
        await cur.execute(
            """
            SELECT
                AVG(output_quality_score)       AS output_quality_avg,
                AVG(execution_efficiency_score) AS efficiency_avg,
                AVG(contractor_attitude_score)  AS attitude_avg,
                COUNT(*)                        AS rating_count
            FROM ratings
            WHERE ratee_id = %s
              AND rating_direction = 'client_to_contractor'
            """,
            (contractor_id,)
        )
        summary = await cur.fetchone()

        # 最近評論
        await cur.execute(
            """
            SELECT overall_comment, rating_date
            FROM ratings
            WHERE ratee_id = %s
              AND rating_direction = 'client_to_contractor'
              AND overall_comment IS NOT NULL
            ORDER BY rating_date DESC
            LIMIT 3
            """,
            (contractor_id,)
        )
        comments = await cur.fetchall()

    return {
        "summary": dict(summary) if summary else None,
        "comments": [dict(c) for c in comments],
    }
