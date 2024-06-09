from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
import mysql.connector
import boto3
import os
from dotenv import load_dotenv
import time
import cv2
import numpy as np
import urllib.request
import urllib.parse
from typing import Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
import aiohttp

load_dotenv()
app = FastAPI()

# Database connection configuration
userdb_config = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME_USER')
}

artdb_config = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME_ART')
}

# 팀원 config
FASTAPI_URL2 = os.getenv('FASTAPI_URL2')

class ArtIDRequest(BaseModel):
    art_id: int

class ArtInfoResponse(BaseModel):
    art_id: int
    art_name: str
    art_artist: Optional[str]
    art_img_url: str

class SaveImgRequest(BaseModel):
    user_img_url: str

class ArtConfirmationRequest(BaseModel):
    art_id: int

# S3 configuration
s3 = boto3.client('s3',
                  aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID_1'),
                  aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY_1'),
                  region_name=os.getenv('AWS_REGION'))
BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME')

def download_image_from_s3(url):
    try:
        resp = urllib.request.urlopen(url)
        image = np.asarray(bytearray(resp.read()), dtype="uint8")
        image = cv2.imdecode(image, cv2.IMREAD_COLOR)
        return image
    except Exception as e:
        print(f"Error downloading image from S3: {e}")
        raise

def resize_image(image, max_size=800):
    try:
        height, width = image.shape[:2]
        if max(height, width) > max_size:
            scaling_factor = max_size / float(max(height, width))
            image = cv2.resize(image, (int(width * scaling_factor), int(height * scaling_factor)))
        return image
    except Exception as e:
        print(f"Error resizing image: {e}")
        raise

def calculate_image_similarity(img1, img2):
    try:
        # SIFT 디텍터 생성
        sift = cv2.SIFT_create()
        kp1, des1 = sift.detectAndCompute(img1, None)
        kp2, des2 = sift.detectAndCompute(img2, None)

        # FLANN 매처 생성
        FLANN_INDEX_KDTREE = 1
        index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
        search_params = dict(checks=50)
        flann = cv2.FlannBasedMatcher(index_params, search_params)
        matches = flann.knnMatch(des1, des2, k=2)

        # 좋은 매치 개수
        good_matches = []
        for m, n in matches:
            if m.distance < 0.7 * n.distance:
                good_matches.append(m)

        num_good_matches = len(good_matches)
        return num_good_matches, kp1, kp2, good_matches
    except Exception as e:
        print(f"Error calculating image similarity: {e}")
        raise

async def compare_images(uploaded_image, art_images):
    max_similarity = -1
    most_similar_art = None
    best_kp1, best_kp2, best_matches = None, None, None

    with ThreadPoolExecutor() as executor:
        loop = asyncio.get_event_loop()
        tasks = []
        for art in art_images:
            tasks.append(loop.run_in_executor(executor, calculate_image_similarity,
                                              uploaded_image, download_image_from_s3(urllib.parse.quote(art['art_img_url'], safe=':/'))))

        results = await asyncio.gather(*tasks)

    for i, (similarity, kp1, kp2, matches) in enumerate(results):
        if similarity > max_similarity:
            max_similarity = similarity
            most_similar_art = art_images[i]
            best_kp1, best_kp2, best_matches = kp1, kp2, matches

    return most_similar_art, best_kp1, best_kp2, best_matches

# 사용자가 입력한 이미지의 S3 객체 주소와 이미지ID를 DB_NAME_USER에 저장하기
@app.post("/saveUserImg")
async def saveUserImg(request: SaveImgRequest):
    try:
        conn = mysql.connector.connect(**userdb_config)
        cursor = conn.cursor()
        query = "INSERT INTO userimg_info (user_img_url) VALUES (%s)"
        cursor.execute(query, (request.user_img_url,))
        conn.commit()
        cursor.close()
        conn.close()
        return {"success": True, "user_img_url": request.user_img_url}
    except mysql.connector.Error as err:
        print(f"Database connection failed: {err}")
        raise HTTPException(status_code=500, detail="Database connection failed")
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# /saveArtImg S3폴더에 있는 이미지들의 이름(파일명)을 MySQL(art)에 있는 art_name에, 객체 주소를 art_img_url에 넣기
@app.get("/s3ToSql")
async def s3_to_sql():
    try:
        response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix='saveArtImg/')
        objects = response.get('Contents', [])
        if not objects:
            return {"success": False, "message": "No objects found in the specified S3 folder"}
        conn = mysql.connector.connect(**artdb_config)
        cursor = conn.cursor()
        for obj in objects:
            if obj['Key'].endswith('/'):
                continue
            try:
                file_name = os.path.basename(obj['Key'])
                file_url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{obj['Key']}"
                cursor.execute("SELECT COUNT(*) FROM art_info WHERE art_img_url = %s", (file_url,))
                count = cursor.fetchone()[0]
                if count == 0:
                    query = "INSERT INTO art_info (art_name, art_img_url) VALUES (%s, %s)"
                    cursor.execute(query, (file_name, file_url))
                    print(f"Successfully inserted: {file_name} - {file_url}")
                else:
                    print(f"Duplicate URL found, skipping: {file_url}")
            except mysql.connector.Error as err:
                print(f"Error inserting {file_name}: {err}")
                continue
        conn.commit()
        cursor.close()
        conn.close()
        return {"success": True, "message": "Art images saved to database"}
    except mysql.connector.Error as err:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {err}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 유사도 체크하는 api
@app.post("/findSimilarArt", response_model=ArtInfoResponse)
async def find_similar_art(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        uploaded_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        uploaded_image = resize_image(uploaded_image)
        conn = mysql.connector.connect(**artdb_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT art_id, art_name, art_artist, art_img_url FROM art_info")
        art_images = cursor.fetchall()
        cursor.close()
        conn.close()
        most_similar_art, best_kp1, best_kp2, best_matches = await compare_images(uploaded_image, art_images)
        if most_similar_art:
            most_similar_art['art_artist'] = most_similar_art.get('art_artist', '')
            return most_similar_art
        else:
            raise HTTPException(status_code=404, detail="No similar art found")
    except mysql.connector.Error as err:
        print(f"Database connection failed: {err}")
        raise HTTPException(status_code=500, detail="Database connection failed")
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 유사한 작품의 art_id를 팀원에게 보내기
@app.post("/postArtInfo")
async def post_art_info(request: ArtConfirmationRequest):
    try:
        art_id = request.art_id
        return {"success": True, "message": "Art ID received", "art_id": art_id}
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# @app.get("/get-art-info/{art_id}", response_model=ArtInfoResponse)
# async def get_art_info(art_id: int):
#     try:
#         conn = mysql.connector.connect(**artdb_config)
#         cursor = conn.cursor(dictionary=True)
#         cursor.execute("SELECT art_id, art_name, art_artist, art_img_url FROM art_info WHERE art_id = %s", (art_id,))
#         art_info = cursor.fetchone()
#         cursor.close()
#         conn.close()

#         if art_info:
#             return art_info
#         else:
#             raise HTTPException(status_code=404, detail="Art ID not found")
#     except mysql.connector.Error as err:
#         print(f"Database connection failed: {err}")
#         raise HTTPException(status_code=500, detail="Database connection failed")
#     except Exception as e:
#         print(f"Unexpected error: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# 팀원이 art_id를 요청하면 MySQL 데이터베이스로부터 정보를 반환하는 API
@app.post("/requestArtID", response_model=ArtInfoResponse)
async def request_art_id(request: ArtConfirmationRequest):
    try:
        art_id = request.art_id

        conn = mysql.connector.connect(**artdb_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT art_id, art_name, art_artist, art_img_url FROM art_info WHERE art_id = %s", (art_id,))
        art_info = cursor.fetchone()
        cursor.close()
        conn.close()

        if art_info:
            # 모델을 사용하여 응답을 생성합니다.
            response = ArtInfoResponse(
                art_id=art_info['art_id'],
                art_name=art_info['art_name'],
                art_artist=art_info['art_artist'],
                art_img_url=art_info['art_img_url']
            )
            return response
        else:
            raise HTTPException(status_code=404, detail="Art ID not found")

    except mysql.connector.Error as err:
        print(f"Database connection failed: {err}")
        raise HTTPException(status_code=500, detail="Database connection failed")
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
