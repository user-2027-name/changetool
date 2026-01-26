import streamlit as st
import pandas as pd
import re
import requests
from io import BytesIO, StringIO
from datetime import date

# --- 1. 共通のデータ変換関数 ---
def transform_data(df):
    # 列名の初期設定 (22列固定)
    df.columns = [f"Column{i+1}" for i in range(len(df.columns))]
    
    # 型の統一とトリミング（空欄を維持するため、一度文字型にする）
    df = df.astype(str).apply(lambda x: x.str.strip())
    # 'nan' 文字列を実際の空文字に置換
    df = df.replace(['nan', 'None', 'None', ''], '')

    # 2. 和暦(年)の抽出と西暦変換
    def extract_year(text):
        match = re.search(r'和\s*(\d+)', str(text))
        return int(match.group(1)) + 2018 if match else None

    df['year_val'] = df['Column1'].apply(extract_year)
    # 文字列の 'None' などを除外してから埋める
    df['year_val'] = df['year_val'].replace('', None).ffill()

    # 3. 氏名と乗務員コードの抽出
    df['氏名'] = df.apply(lambda x: x['Column2'] if "氏名" in str(x['Column1']) else None, axis=1)
    df['乗務員コード'] = df.apply(lambda x: x['Column4'] if "コード" in str(x['Column3']) else None, axis=1)
    df[['氏名', '乗務員コード']] = df[['氏名', '乗務員コード']].replace('', None).ffill()

    # 4. 月・日の抽出と日付作成
    def create_date(row):
        text = str(row['Column1'])
        match = re.search(r'(\d+)月\s*(\d+)日', text)
        if match and pd.notnull(row['year_val']):
            try:
                # ここで日付を YYYY/MM/DD の文字列形式に変換
                d = date(int(row['year_val']), int(match.group(1)), int(match.group(2)))
                return d.strftime('%Y/%m/%d')
            except:
                return ""
        return ""

    df['日付'] = df.apply(create_date, axis=1)

    # 5. 不要な行の削除
    ignore_keywords = ["累計拘束時間", "D2 :", "最大拘束時間", "事業所", "令和", "日付", "氏名"]
    df = df[df['日付'] != ""]
    for kw in ignore_keywords:
        df = df[~df['Column1'].str.contains(kw, na=False)]

    # 6. リネーム
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
    
    # 7. 最終整形
    final_cols = ["乗務員コード", "氏名", "日付"] + [c for c in rename_dict.values() if c in df.columns]
    
    # 最後の仕上げ：データフレーム全体の nan を空文字に統一
    res = df[final_cols].replace(['nan', 'None', 'nan', None], '')
    return res

# --- 2. Streamlit Web画面 ---
st.set_page_config(page_title="拘束時間管理変換ツール", layout="wide")
st.title("🚛 拘束時間管理表 変換ツール")

tab1, tab2 = st.tabs(["📤 CSVファイルをD&D", "🌐 APIから取得"])

processed_df = None

with tab1:
    uploaded_file = st.file_uploader("ここにCSVファイルをドロップしてください", type="csv")
    if uploaded_file:
        df_input = pd.read_csv(
            uploaded_file, 
            encoding='cp932', 
            header=None, 
            names=range(22), 
            engine='python'
        )
        processed_df = transform_data(df_input)

with tab2:
    api_url = st.text_input("API URL", value="https://example.com/api/data")
    if st.button("APIを実行"):
        try:
            response = requests.get(api_url)
            response.raise_for_status()
            df_input = pd.read_csv(
                StringIO(response.text), 
                header=None, 
                names=range(22), 
                engine='python'
            )
            processed_df = transform_data(df_input)
            st.success("API取得成功！")
        except Exception as e:
            st.error(f"エラー: {e}")

# --- 3. プレビューとダウンロード ---
if processed_df is not None:
    st.divider()
    st.subheader("✅ 変換完了プレビュー")
    st.dataframe(processed_df)

    # Excelダウンロード
    output = BytesIO()
    # Excel書き出し時に空欄が 'nan' にならないよう設定
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        processed_df.to_excel(writer, index=False, sheet_name='Sheet1')
    
    st.download_button(
        label="📥 変換済みExcelをダウンロード",
        data=output.getvalue(),
        file_name=f"拘束時間管理表_{date.today()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )