import streamlit as st
import pandas as pd
import re
import requests
from io import BytesIO, StringIO
from datetime import date, timedelta

# --- 1. Excel変換用の補助関数 ---
def time_str_to_timedelta(time_str):
    """'13:30' を Excelが計算可能なtimedeltaオブジェクトに変換"""
    if not time_str or ':' not in str(time_str):
        return None
    try:
        # 文字列を時と分に分解
        h, m = map(int, str(time_str).split(':'))
        return timedelta(hours=h, minutes=m)
    except:
        return None

# --- 2. 共通のデータ変換関数 ---
def transform_data(df):
    # 列名の初期設定
    df.columns = [f"Column{i+1}" for i in range(len(df.columns))]
    
    # 型の統一とトリミング
    df = df.astype(str).apply(lambda x: x.str.strip())
    df = df.replace(['nan', 'None', ''], '')

    # 和暦の抽出と西暦変換
    def extract_year(text):
        match = re.search(r'和\s*(\d+)', str(text))
        return int(match.group(1)) + 2018 if match else None

    df['year_val'] = df['Column1'].apply(extract_year)
    df['year_val'] = df['year_val'].replace('', None).ffill()

    # 氏名と乗務員コードの抽出
    df['氏名'] = df.apply(lambda x: x['Column2'] if "氏名" in str(x['Column1']) else None, axis=1)
    df['乗務員コード'] = df.apply(lambda x: x['Column4'] if "コード" in str(x['Column3']) else None, axis=1)
    df[['氏名', '乗務員コード']] = df[['氏名', '乗務員コード']].replace('', None).ffill()

    # 日付作成
    def create_date(row):
        text = str(row['Column1'])
        match = re.search(r'(\d+)月\s*(\d+)日', text)
        if match and pd.notnull(row['year_val']):
            try:
                return date(int(row['year_val']), int(match.group(1)), int(match.group(2)))
            except:
                return ""
        return ""

    df['日付'] = df.apply(create_date, axis=1)

    # 不要な行の削除
    ignore_keywords = ["累計拘束時間", "D2 :", "最大拘束時間", "事業所", "令和", "日付", "氏名"]
    df = df[df['日付'] != ""]
    for kw in ignore_keywords:
        df = df[~df['Column1'].str.contains(kw, na=False)]

    # 22列のリネーム（全項目維持）
    rename_dict = {
        "Column2": "始業時刻", "Column3": "終業時刻", "Column4": "運転時間",
        "Column5": "重複運転時間", "Column6": "荷役時間", "Column7": "重複荷役時間",
        "Column8": "休憩時間", "Column9": "重複休憩時間", "Column10": "拘束時間小計",
        "Column11": "重複拘束時間小計", "Column12": "拘束時間合計", "Column13": "拘束時間累計",
        "Column14": "前運転平均", "Column15": "後運転平均", "Column16": "休息時間",
        "Column17": "実働時間", "Column18": "時間外時間", "Column19": "深夜時間",
        "Column20": "時間外深夜時間", "Column21": "摘要1", "Column22": "摘要2"
    }
    df = df.rename(columns=rename_dict)
    
    final_cols = ["乗務員コード", "氏名", "日付"] + [c for c in rename_dict.values() if c in df.columns]
    return df[final_cols].replace(['nan', 'None', None], '')

# --- 3. Streamlit Web画面 ---
st.set_page_config(page_title="拘束時間管理変換ツール", layout="wide")
st.title("🚛 拘束時間管理表 変換ツール")

tab1, tab2 = st.tabs(["📤 CSVファイルをD&D", "🌐 APIから取得"])
processed_df = None

with tab1:
    uploaded_file = st.file_uploader("ここにCSVファイルをドロップしてください", type="csv")
    if uploaded_file:
        df_input = pd.read_csv(uploaded_file, encoding='cp932', header=None, names=range(22), engine='python')
        processed_df = transform_data(df_input)

with tab2:
    api_url = st.text_input("API URL", value="")
    if st.button("APIを実行"):
        try:
            response = requests.get(api_url)
            response.raise_for_status()
            df_input = pd.read_csv(StringIO(response.text), header=None, names=range(22), engine='python')
            processed_df = transform_data(df_input)
            st.success("API取得成功！")
        except Exception as e:
            st.error(f"APIエラー: {e}")

if processed_df is not None:
    st.divider()
    st.subheader("✅ 変換完了プレビュー")
    st.dataframe(processed_df, use_container_width=True)

    # --- Excelダウンロード処理 ---
    st.divider()
    output = BytesIO()
    try:
        # Excel用にコピーを作成
        export_df = processed_df.copy()
        # 時間計算が必要な列（数値・時間型の列）
        time_cols = [
            "始業時刻", "終業時刻", "運転時間", "重複運転時間", "荷役時間", 
            "重複荷役時間", "休憩時間", "重複休憩時間", "拘束時間小計", 
            "重複拘束時間小計", "拘束時間合計", "拘束時間累計", "休息時間", 
            "実働時間", "時間外時間", "深夜時間", "時間外深夜時間"
        ]
        
        # 内部データをtimedelta型へ変換
        for col in time_cols:
            if col in export_df.columns:
                export_df[col] = export_df[col].apply(time_str_to_timedelta)

        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            export_df.to_excel(writer, index=False, sheet_name='Sheet1')
            workbook = writer.book
            worksheet = writer.sheets['Sheet1']
            
            # 🌟 指定の表示形式 [h]:mm を設定
            h_mm_format = workbook.add_format({'num_format': '[h]:mm'})
            
            # Excelの各列をループして、時間列にのみフォーマットを適用
            for i, col_name in enumerate(export_df.columns):
                if col_name in time_cols:
                    # 列の幅を自動調整しつつフォーマット適用
                    worksheet.set_column(i, i, 12, h_mm_format)

        st.download_button(
            label="📥 計算用Excel ([h]:mm) をダウンロード",
            data=output.getvalue(),
            file_name=f"拘束時間管理表_{date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        st.error(f"Excel作成エラー: {e}")
