# app/routes/search.py
from flask import Blueprint, request, jsonify, render_template
from sqlalchemy import text
from app.extensions import db  # 팀원이 만든 공통 db 객체 불러오기

# 블루프린트 생성
search_bp = Blueprint('search', __name__, url_prefix='/api')

@search_bp.route('/search', methods=['GET'])
def search_page():
    return render_template('search.html')

@search_bp.route('/api/search', methods=['GET'])
def search_movies():
    query_param = request.args.get('query', '').strip()
    if not query_param:
        return jsonify({"status": "success", "data": []})

    try:
        sql = text("""
            SELECT DISTINCT m.id, mt.title, m.poster_url, m.overview
            FROM movies m
            JOIN movie_titles mt ON m.id = mt.movie_id
            WHERE mt.title ILIKE :search_term
               OR m.original_title ILIKE :search_term
            LIMIT 20
        """)
        result = db.session.execute(sql, {"search_term": f"%{query_param}%"})
        
        movies = []
        for row in result:
            movies.append({
                "id": str(row.id),
                "title": row.title,
                "poster_url": row.poster_url,
                "overview": row.overview
            })
            
        return jsonify({"status": "success", "data": movies})
    except Exception as e:
        print(f"Search Error: {e}")
        return jsonify({"status": "error", "message": "검색 중 오류 발생"}), 500