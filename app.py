import os
import re
import io
import pandas as pd
import pdfplumber
from flask import Flask, request, send_file, render_template_string

app = Flask(__name__)

# 디자인 및 UI를 구성하는 HTML/CSS 코드
# 첨부해주신 로고가 가려지지 않도록 컨테이너를 약간 아래쪽으로 배치하고 반투명하게 설정했습니다.
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YOON & AHN Customs - 인보이스 변환기</title>
    <style>
        body {
            /* 업로드한 이미지를 배경으로 사용 */
            background-image: url('/static/background.jpg');
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-color: #5a3a22; /* 이미지 로딩 전 기본 브라운 컬러 */
            height: 100vh;
            margin: 0;
            display: flex;
            flex-direction: column;
            justify-content: flex-end; /* 로고가 보이도록 박스를 아래로 내림 */
            align-items: center;
            padding-bottom: 15vh; 
            font-family: 'Malgun Gothic', sans-serif;
        }
        .container {
            background-color: rgba(255, 255, 255, 0.9); /* 가독성을 위한 반투명 흰색 배경 */
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 8px 16px rgba(0,0,0,0.3);
            text-align: center;
            max-width: 500px;
            width: 90%;
        }
        h1 { 
            color: #5a3a22; 
            margin-top: 0;
            font-size: 24px;
        }
        p { color: #333; }
        .upload-btn {
            background-color: #5a3a22;
            color: white;
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            margin-top: 20px;
            transition: background-color 0.3s ease;
        }
        .upload-btn:hover { background-color: #3e2615; }
        input[type="file"] { 
            margin-top: 20px; 
            font-size: 15px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📄 ENCOM 엑셀 자동 변환</h1>
        <p>인보이스 PDF 파일을 업로드하시면<br>데이터가 추출되어 엑셀 파일로 바로 다운로드됩니다.</p>
        <form action="/upload" method="post" enctype="multipart/form-data">
            <input type="file" name="file" accept=".pdf" required>
            <br>
            <button type="submit" class="upload-btn">변환 및 다운로드</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    # 첫 화면에 HTML 템플릿을 보여줍니다.
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload_file():
    # 파일 업로드 확인
    if 'file' not in request.files:
        return "파일이 업로드되지 않았습니다.", 400
    file = request.files['file']
    if file.filename == '':
        return "선택된 파일이 없습니다.", 400
    
    # PDF 파일인지 확인 후 처리
    if file and file.filename.lower().endswith('.pdf'):
        items_list = []
        
        # 파일 메모리에서 바로 읽기
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                    
                lines = text.split('\n')
                temp_desc = ""
                
                for line in lines:
                    if "PHOTOMASK" in line or "EB6X-NIK" in line:
                        if "PC" not in line:
                            temp_desc = line.strip()
                    
                    if "PC" in line and "USD" in line:
                        parts = line.split()
                        try:
                            amount_val = parts[-1]
                            up_val = parts[-2]
                            if up_val == 'USD':
                                up_val = parts[-3]
                                
                            um_val = "PC"
                            pc_index = parts.index("PC")
                            qty_val = parts[pc_index - 1]
                            mask_name_val = parts[pc_index - 2]
                            
                            item_no = parts[0]
                            if not item_no.isdigit():
                                item_no = "1"
                                
                            code_parts = parts[1:pc_index - 2]
                            item_code = " ".join(code_parts)
                            
                            if temp_desc and temp_desc not in item_code:
                                item_code = f"{temp_desc} {item_code}".strip()
                            elif not item_code and temp_desc:
                                item_code = temp_desc
                                
                            items_list.append({
                                "ITEM": item_no,
                                "Item Code(Pre PR)": item_code.replace("PHOTOMASK EB6X-NIK EB6X-NIK", "PHOTOMASK EB6X-NIK"),
                                "MASK NAME": mask_name_val,
                                "Q'TY": qty_val,
                                "U/M": um_val,
                                "U/P": up_val,
                                "AMOUNT": amount_val,
                                "Term": "USD"
                            })
                            temp_desc = "" 
                        except Exception:
                            pass 
                            
        if not items_list:
            return "<script>alert('PDF에서 추출할 품목 데이터를 찾지 못했습니다.'); history.back();</script>", 400
            
        # 추출한 데이터를 DataFrame으로 변환
        df = pd.DataFrame(items_list)
        
        # 엑셀 파일을 디스크에 저장하지 않고 메모리(BytesIO)에 기록하여 바로 다운로드
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Invoice_Items')
        
        output.seek(0)
        
        # 파일 이름 설정 및 다운로드 반환
        download_name = file.filename.replace('.pdf', '_ENCOM.xlsx')
        return send_file(
            output,
            as_attachment=True,
            download_name=download_name,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    return "<script>alert('잘못된 파일 형식입니다. PDF 파일을 업로드해주세요.'); history.back();</script>", 400

if __name__ == '__main__':
    # 웹 서버 실행 (브라우저에서 http://127.0.0.1:5000 으로 접속)
    app.run(debug=True, port=5000)
