import csv
import re
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from collections import defaultdict

app = Flask(__name__)
CORS(app)

# SQLiteデータベースの設定
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///similar_groups.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# データベースモデルの定義
class SimilarGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_code = db.Column(db.String(80), nullable=False)
    classification = db.Column(db.String(120), nullable=False)
    general_similar = db.Column(db.Boolean, nullable=False)
    remark_similar = db.Column(db.Boolean, nullable=False)
    related_codes = db.Column(db.String(500), nullable=True)  # 追加: related_codes列を定義

    # 複合ユニーク制約を設定
    __table_args__ = (db.UniqueConstraint('group_code', 'classification', name='unique_group_classification'),)

@app.route('/')
def index():
    return render_template('form.html')

@app.route('/search', methods=['POST'])
def search_classification():
    data = request.get_json()
    group_codes = data.get('group_code')

    # スペースなどを取り除き、形式を修正
    cleaned_codes = re.sub(r'\s+', ' ', group_codes).upper().split()
    print(f"Cleaned Group Codes: {cleaned_codes}")  # デバッグ用

    classifications = defaultdict(set)
    remark_classifications = defaultdict(set)
    related_codes_dict = defaultdict(list)  # 35K関連のコードを保持するための辞書

    for cleaned_code in cleaned_codes:
        # 正しい形式（2桁数字 + アルファベット文字 + 2桁数字）であるか確認
        match = re.fullmatch(r'\d{2}[A-Z]\d{2}', cleaned_code)
        if not match:
            return jsonify({"error": "類似群コードの形式が正しくありません。"}), 400

        # 入力された類似群コードに対応する区分を検索
        similar_groups = SimilarGroup.query.filter_by(group_code=cleaned_code).all()
        if similar_groups:
            for group in similar_groups:
                if group.general_similar:
                    if group.classification == "第35類（小売）" and group.related_codes:
                        # 関連コードがある場合、それらも一緒に保持
                        related_codes_dict[group.group_code].extend(group.related_codes.split())
                    classifications[group.classification].add(cleaned_code)
                if group.remark_similar:
                    remark_classifications[group.classification].add(cleaned_code)
        else:
            print(f"No matching group found for: {cleaned_code}")  # デバッグ用

    if classifications or remark_classifications:
        result = []
        for classification, codes in classifications.items():
            group_code_list = []
            for code in codes:
                # 関連コードがある場合には括弧内に追加する
                if code in related_codes_dict:
                    related = " ".join(related_codes_dict[code])
                    group_code_list.append(f"{code} ({related})")
                else:
                    group_code_list.append(code)
            result.append({"classification": classification, "group_codes": group_code_list})
        sorted_result = sorted(result, key=lambda x: int(re.search(r'\d+', x["classification"]).group()) if re.search(r'\d+', x["classification"]) else x["classification"])

        remark_result = []
        for classification, codes in remark_classifications.items():
            remark_result.append({"classification": classification, "group_codes": list(codes)})
        sorted_remark_result = sorted(remark_result, key=lambda x: int(re.search(r'\d+', x["classification"]).group()) if re.search(r'\d+', x["classification"]) else x["classification"])

        return jsonify({"classification_details": sorted_result, "remark_details": sorted_remark_result})
    else:
        return jsonify({"error": "該当する区分が見つかりませんでした。"}), 404

# データベースの初期化とCSVからのデータ読み込み
if __name__ == '__main__':
    with app.app_context():
        # 既存のテーブルを削除して再作成
        db.drop_all()
        db.create_all()

        # データが既に存在しているかチェックし、なければ追加する
        with open('similar_groups.csv', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # データベース内にすでに存在するか確認
                existing_group = SimilarGroup.query.filter_by(
                    group_code=row['group_code'].strip(),
                    classification=row['classification']
                ).first()

                if not existing_group:
                    related_codes = row.get('related_codes')
                    new_group = SimilarGroup(
                        group_code=row['group_code'].strip(),
                        classification=row['classification'],
                        general_similar=(row['general_similar'].strip().lower() == 'yes'),
                        remark_similar=(row['remark_similar'].strip().lower() == 'yes'),
                        related_codes=related_codes.strip() if related_codes and related_codes.strip() else None  # related_codes列を追加
                    )
                    db.session.add(new_group)

            db.session.commit()

    app.run(debug=True)
