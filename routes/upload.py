from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, Request, Depends
from pydantic import BaseModel
from typing import List, Optional, Union
import json
from datetime import datetime
from routes.database import passage,DILRquestion,VARCquestion,QAquestion , test , user
from routes.database import get_db
from routes.auth import verify_token
from google.cloud import storage
import os
from bson.objectid import ObjectId
from google.oauth2 import service_account

cloud_storage_credentials_str = os.getenv("CLOUD_STORAGE_CREDENTIALS", "{}")
service_account_info = json.loads(cloud_storage_credentials_str)
credentials = service_account.Credentials.from_service_account_info(service_account_info)

client = storage.Client(credentials=credentials, project=service_account_info["project_id"])
# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "ci-0992c46cc6dd.json"
# client = storage.Client()
bucket = client.bucket("examinobucket")

router = APIRouter(prefix="/upload", tags=["upload"])

def uploadimage(file):
    print(file.filename)
    blob = bucket.blob(file.filename)
    # Read file content and upload as bytes
    file_content = file.file.read()
    blob.upload_from_string(file_content, content_type=file.content_type)
    print(blob.public_url)
    return {"url": blob.public_url}

class PreviousYear(BaseModel):
    exam: str
    year: int
    slot: str

class Passage(BaseModel):
    title: str
    section: str
    Domain: str
    area: List[str]
    body: str
    media: Optional[str] = None
    previous_year: Optional[PreviousYear] = None

class VARCques(BaseModel):
    para_id: Optional[str] = None
    section: str
    Domain: str
    area: List[str]
    text: str
    difficulty: str
    formulaable: bool
    media: Optional[str] = None
    choices: List[str]
    answer: str
    canBeTITA: bool

class DILRques(BaseModel):
    para_id: Optional[str] = None
    section: str
    Domain: str
    area: List[str]
    text: str
    difficulty: str
    formulaable: bool
    media: Optional[str] = None
    choices: List[str]
    answer: str
    canBeTITA: bool

class QAques(BaseModel):
    section: str
    Domain: str
    area: List[str]
    text: str
    difficulty: str
    formulaable: bool
    media: Optional[str] = None
    choices: List[str]
    answer: str
    canBeTITA: bool

class PassageResponse(BaseModel):
    id: str

@router.post("/passage", response_model=PassageResponse)
async def upload_passage(passage_data: str = Form(...), file: UploadFile = File(None), current_user: str = Depends(verify_token)):
    passage_dict = json.loads(passage_data)
    if file:
        media_url = uploadimage(file)
        passage_dict["media"] = media_url["url"]
    passage_dict["createdAt"] = datetime.now().isoformat()
    passage_dict["question_id"] = {"E": [], "M": [], "H": []}
    result = passage.insert_one(passage_dict)
    return {"id": str(result.inserted_id)}

class QuestionResponse(BaseModel):
    id: str

@router.post("/varc", response_model=QuestionResponse)
async def upload_varc_question(question_data: str = Form(...), file: UploadFile = File(None), current_user: str = Depends(verify_token)):
    question_dict = json.loads(question_data)
    if file:
        media_url = uploadimage(file)
        question_dict["media"] = media_url["url"]
    result = VARCquestion.insert_one(question_dict)
    if question_dict.get("para_id"):
        print("happending")
        passage.update_one({"_id": ObjectId(question_dict["para_id"])}, {"$push": {f"question_id.{question_dict['difficulty']}": result.inserted_id}})
    return {"id": str(result.inserted_id)}

@router.post("/dilr", response_model=QuestionResponse)
async def upload_dilr_question(question_data: str = Form(...), file: UploadFile = File(None), current_user: str = Depends(verify_token)):
    question_dict = json.loads(question_data)
    if file:
        media_url = uploadimage(file)
        question_dict["media"] = media_url["url"]
    result = DILRquestion.insert_one(question_dict)
    if question_dict.get("para_id"):
        passage.update_one({"_id": ObjectId(question_dict["para_id"])}, {"$push": {f"question_id.{question_dict['difficulty']}": result.inserted_id}})
    return {"id": str(result.inserted_id)}

@router.post("/qa", response_model=QuestionResponse)
async def upload_qa_question(question_data: str = Form(...), file: UploadFile = File(None), current_user: str = Depends(verify_token)):
    question_dict = json.loads(question_data)
    if file:
        media_url = uploadimage(file)
        question_dict["media"] = media_url["url"]
    result = QAquestion.insert_one(question_dict)
    return {"id": str(result.inserted_id)}


@router.get("/testoverview")
async def get_test_overview(current_user: str = Depends(verify_token)):
    found_user = user.find_one({"email": current_user})
    if not found_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    test_ids = found_user.get("test_id", [])
    test_data = []
    for test_id in test_ids:
        t1 = test.find_one({"_id": test_id})
        if not t1:
            continue
        t1.pop('test_config', None)
        t1.pop('sections', None)
        t1.pop('questionDetails', None)

        # convert ObjectId to str if needed
        if "_id" in t1:
            t1["_id"] = str(t1["_id"])
        test_data.append(t1)
    #print(test_data)
    return test_data

@router.post("/testresultdetail")
async def get_test_result_detail(request: Request, current_user: str = Depends(verify_token)):
    data = await request.json()
    found_user = user.find_one({"email": current_user})
    if not found_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    print(data["test_id"])
    test_data = test.find_one({"_id": ObjectId(data["test_id"])})
    if not test_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found"
        )
    test_data['_id'] = str(test_data['_id'])
    print(test_data)
    return test_data

@router.post("/testresult")
async def upload_test(request: Request, current_user: str = Depends(verify_token)):
    data = await request.json()
    test_id = test.insert_one(data)
    print(data)
    print(test_id.inserted_id)
    user.update_one({"email": current_user}, {"$push": {"test_id": test_id.inserted_id}, "$inc": { "trail": -1 } })
    us = user.find_one({"email": current_user})
    if not us:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    user_dashboard = us["dashboardAnalytics"]

    #print(user_dashboard)

    user_dashboard['Tests Taken'] += 1
    user_dashboard['Test Time'] += data.get("overallTimeSpent", 0)
    user_dashboard['Questions Attempted'] += data.get("totalQuestions", 0)
    questions_attempted = user_dashboard['Questions Attempted']
    if questions_attempted > 0:
        avg_seconds = user_dashboard['Test Time'] / questions_attempted
    else:
        avg_seconds = 0.0
    user_dashboard['_AvgTimePerQ_seconds'] = avg_seconds
    mins = int(avg_seconds // 60)
    secs = int(avg_seconds % 60)
    user_dashboard['Avg. Time/Q'] = f"{mins}:{secs:02d}"
    print("--------------------------------")
    user_dashboard['Accuracy'] = (((user_dashboard['Tests Taken']-1)*int(user_dashboard['Accuracy'])) + ((data["correctAnswers"]*100)/data['totalQuestions']))/user_dashboard['Tests Taken']

    if data['sections']['VARC']['questions'] > 0:
        user_dashboard['PerformanceTrend']['VARC'].append(data['sections']['VARC']['accuracy'])
        user_dashboard['PerformanceTrend']['VARC'].pop(0)

        # old totals
        prev_correct = user_dashboard['Total Question Solved']['VARC']['T_correct']
        prev_incorrect = user_dashboard['Total Question Solved']['VARC']['T_incorrect']
        prev_na = user_dashboard['Total Question Solved']['VARC']['T_NA']
        prev_total_qs = prev_correct + prev_incorrect + prev_na
        prev_total_time = prev_total_qs * user_dashboard['Total Question Solved']['VARC']['AvgTime']

        # update counts
        new_correct = data['sections']['VARC']['correct']
        new_incorrect = data['sections']['VARC']['incorrect']
        new_na = data['sections']['VARC']['unattempted']
        new_total_qs = new_correct + new_incorrect + new_na
        new_total_time = data['sections']['VARC']['timeSpent']

        user_dashboard['Total Question Solved']['VARC']['T_correct'] += new_correct
        user_dashboard['Total Question Solved']['VARC']['T_incorrect'] += new_incorrect
        user_dashboard['Total Question Solved']['VARC']['T_NA'] += new_na

        # recalc averages
        total_qs = prev_total_qs + new_total_qs
        total_time = prev_total_time + new_total_time
        user_dashboard['Total Question Solved']['VARC']['AvgTime'] = total_time / total_qs if total_qs > 0 else 0

        # AvgTime_C
        denom_c = prev_correct + new_correct
        if denom_c > 0:
            user_dashboard['Total Question Solved']['VARC']['AvgTime_C'] = ((prev_correct * user_dashboard['Total Question Solved']['VARC']['AvgTime_C']) + (new_correct * data['sections']['VARC']['timeSpentCorrect'])) / denom_c
        # AvgTime_I
        denom_i = prev_incorrect + new_incorrect
        if denom_i > 0:
            user_dashboard['Total Question Solved']['VARC']['AvgTime_I'] = ((prev_incorrect * user_dashboard['Total Question Solved']['VARC']['AvgTime_I']) + (new_incorrect * data['sections']['VARC']['timeSpentIncorrect'])) / denom_i
        # AvgTime_NA
        denom_na = prev_na + new_na
        if denom_na > 0:
            user_dashboard['Total Question Solved']['VARC']['AvgTime_NA'] = ((prev_na * user_dashboard['Total Question Solved']['VARC']['AvgTime_NA']) + (new_na * data['sections']['VARC']['timeSpentUnattempted'])) / denom_na

        topics = list(data['sections']['VARC']['topics'].keys())
        print(topics)
        for sdq in topics:
            E_C = user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['E']['C']
            E_I = user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['E']['I']
            E_NA = user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['E']['NA']
            M_C = user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['M']['C']
            M_I = user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['M']['I']
            M_NA = user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['M']['NA']
            H_C = user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['H']['C']
            H_I = user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['H']['I']
            H_NA = user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['H']['NA']

            user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['E']['C'] = [E_C[0] + data['sections']['VARC']['topics'][sdq]['easyCorrect'] , E_C[1] + data['sections']['VARC']['topics'][sdq]['easyCorrectTotalTime']]
            user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['E']['I'] = [E_I[0] + data['sections']['VARC']['topics'][sdq]['easyIncorrect'] , E_I[1] + data['sections']['VARC']['topics'][sdq]['easyIncorrectTotalTime']]
            user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['E']['NA'] = [E_NA[0] + data['sections']['VARC']['topics'][sdq]['easyNA'] , E_NA[1] + data['sections']['VARC']['topics'][sdq]['easyNATotalTime']]
            user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['M']['C'] = [M_C[0] + data['sections']['VARC']['topics'][sdq]['mediumCorrect'] , M_C[1] + data['sections']['VARC']['topics'][sdq]['mediumCorrectTotalTime']]
            user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['M']['I'] = [M_I[0] + data['sections']['VARC']['topics'][sdq]['mediumIncorrect'] , M_I[1] + data['sections']['VARC']['topics'][sdq]['mediumIncorrectTotalTime']]
            user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['M']['NA'] = [M_NA[0] + data['sections']['VARC']['topics'][sdq]['mediumNA'] , M_NA[1] + data['sections']['VARC']['topics'][sdq]['mediumNATotalTime']]
            user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['H']['C'] = [H_C[0] + data['sections']['VARC']['topics'][sdq]['hardCorrect'] , H_C[1] + data['sections']['VARC']['topics'][sdq]['hardCorrectTotalTime']]
            user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['H']['I'] = [H_I[0] + data['sections']['VARC']['topics'][sdq]['hardIncorrect'] , H_I[1] + data['sections']['VARC']['topics'][sdq]['hardIncorrectTotalTime']]
            user_dashboard['Total Question Solved']['VARC']['section_breakdown'][sdq]['H']['NA'] = [H_NA[0] + data['sections']['VARC']['topics'][sdq]['hardNA'] , H_NA[1] + data['sections']['VARC']['topics'][sdq]['hardNATotalTime']]

    if data['sections']['DILR']['questions'] > 0:
        user_dashboard['PerformanceTrend']['DILR'].append(data['sections']['DILR']['accuracy'])
        user_dashboard['PerformanceTrend']['DILR'].pop(0)

        # old totals
        prev_correct = user_dashboard['Total Question Solved']['DILR']['T_correct']
        prev_incorrect = user_dashboard['Total Question Solved']['DILR']['T_incorrect']
        prev_na = user_dashboard['Total Question Solved']['DILR']['T_NA']
        prev_total_qs = prev_correct + prev_incorrect + prev_na
        prev_total_time = prev_total_qs * user_dashboard['Total Question Solved']['DILR']['AvgTime']

        # update counts
        new_correct = data['sections']['DILR']['correct']
        new_incorrect = data['sections']['DILR']['incorrect']
        new_na = data['sections']['DILR']['unattempted']
        new_total_qs = new_correct + new_incorrect + new_na
        new_total_time = data['sections']['DILR']['timeSpent']

        user_dashboard['Total Question Solved']['DILR']['T_correct'] += new_correct
        user_dashboard['Total Question Solved']['DILR']['T_incorrect'] += new_incorrect
        user_dashboard['Total Question Solved']['DILR']['T_NA'] += new_na

        # recalc averages
        total_qs = prev_total_qs + new_total_qs
        total_time = prev_total_time + new_total_time
        user_dashboard['Total Question Solved']['DILR']['AvgTime'] = total_time / total_qs if total_qs > 0 else 0

        # AvgTime_C
        denom_c = prev_correct + new_correct
        if denom_c > 0:
            user_dashboard['Total Question Solved']['DILR']['AvgTime_C'] = ((prev_correct * user_dashboard['Total Question Solved']['DILR']['AvgTime_C']) + (new_correct * data['sections']['DILR']['timeSpentCorrect'])) / denom_c
        # AvgTime_I
        denom_i = prev_incorrect + new_incorrect
        if denom_i > 0:
            user_dashboard['Total Question Solved']['DILR']['AvgTime_I'] = ((prev_incorrect * user_dashboard['Total Question Solved']['DILR']['AvgTime_I']) + (new_incorrect * data['sections']['DILR']['timeSpentIncorrect'])) / denom_i
        # AvgTime_NA
        denom_na = prev_na + new_na
        if denom_na > 0:
            user_dashboard['Total Question Solved']['DILR']['AvgTime_NA'] = ((prev_na * user_dashboard['Total Question Solved']['DILR']['AvgTime_NA']) + (new_na * data['sections']['DILR']['timeSpentUnattempted'])) / denom_na


        topics = list(data['sections']['DILR']['topics'].keys())
        print(topics)
        for sdq in topics:
            E_C = user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['E']['C']
            E_I = user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['E']['I']
            E_NA = user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['E']['NA']
            M_C = user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['M']['C']
            M_I = user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['M']['I']
            M_NA = user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['M']['NA']
            H_C = user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['H']['C']
            H_I = user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['H']['I']
            H_NA = user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['H']['NA']

            user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['E']['C'] = [E_C[0] + data['sections']['DILR']['topics'][sdq]['easyCorrect'] , E_C[1] + data['sections']['DILR']['topics'][sdq]['easyCorrectTotalTime']]
            user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['E']['I'] = [E_I[0] + data['sections']['DILR']['topics'][sdq]['easyIncorrect'] , E_I[1] + data['sections']['DILR']['topics'][sdq]['easyIncorrectTotalTime']]
            user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['E']['NA'] = [E_NA[0] + data['sections']['DILR']['topics'][sdq]['easyNA'] , E_NA[1] + data['sections']['DILR']['topics'][sdq]['easyNATotalTime']]
            user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['M']['C'] = [M_C[0] + data['sections']['DILR']['topics'][sdq]['mediumCorrect'] , M_C[1] + data['sections']['DILR']['topics'][sdq]['mediumCorrectTotalTime']]
            user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['M']['I'] = [M_I[0] + data['sections']['DILR']['topics'][sdq]['mediumIncorrect'] , M_I[1] + data['sections']['DILR']['topics'][sdq]['mediumIncorrectTotalTime']]
            user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['M']['NA'] = [M_NA[0] + data['sections']['DILR']['topics'][sdq]['mediumNA'] , M_NA[1] + data['sections']['DILR']['topics'][sdq]['mediumNATotalTime']]
            user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['H']['C'] = [H_C[0] + data['sections']['DILR']['topics'][sdq]['hardCorrect'] , H_C[1] + data['sections']['DILR']['topics'][sdq]['hardCorrectTotalTime']]
            user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['H']['I'] = [H_I[0] + data['sections']['DILR']['topics'][sdq]['hardIncorrect'] , H_I[1] + data['sections']['DILR']['topics'][sdq]['hardIncorrectTotalTime']]
            user_dashboard['Total Question Solved']['DILR']['section_breakdown'][sdq]['H']['NA'] = [H_NA[0] + data['sections']['DILR']['topics'][sdq]['hardNA'] , H_NA[1] + data['sections']['DILR']['topics'][sdq]['hardNATotalTime']]

    if data['sections']['QA']['questions'] > 0:
        user_dashboard['PerformanceTrend']['QA'].append(data['sections']['QA']['accuracy'])
        user_dashboard['PerformanceTrend']['QA'].pop(0)

        # old totals
        prev_correct = user_dashboard['Total Question Solved']['QA']['T_correct']
        prev_incorrect = user_dashboard['Total Question Solved']['QA']['T_incorrect']
        prev_na = user_dashboard['Total Question Solved']['QA']['T_NA']
        prev_total_qs = prev_correct + prev_incorrect + prev_na
        prev_total_time = prev_total_qs * user_dashboard['Total Question Solved']['QA']['AvgTime']

        # update counts
        new_correct = data['sections']['QA']['correct']
        new_incorrect = data['sections']['QA']['incorrect']
        new_na = data['sections']['QA']['unattempted']
        new_total_qs = new_correct + new_incorrect + new_na
        new_total_time = data['sections']['QA']['timeSpent']

        user_dashboard['Total Question Solved']['QA']['T_correct'] += new_correct
        user_dashboard['Total Question Solved']['QA']['T_incorrect'] += new_incorrect
        user_dashboard['Total Question Solved']['QA']['T_NA'] += new_na

        # recalc averages
        total_qs = prev_total_qs + new_total_qs
        total_time = prev_total_time + new_total_time
        user_dashboard['Total Question Solved']['QA']['AvgTime'] = total_time / total_qs if total_qs > 0 else 0

        # AvgTime_C
        denom_c = prev_correct + new_correct
        if denom_c > 0:
            user_dashboard['Total Question Solved']['QA']['AvgTime_C'] = ((prev_correct * user_dashboard['Total Question Solved']['QA']['AvgTime_C']) + (new_correct * data['sections']['QA']['timeSpentCorrect'])) / denom_c
        # AvgTime_I
        denom_i = prev_incorrect + new_incorrect
        if denom_i > 0:
            user_dashboard['Total Question Solved']['QA']['AvgTime_I'] = ((prev_incorrect * user_dashboard['Total Question Solved']['QA']['AvgTime_I']) + (new_incorrect * data['sections']['QA']['timeSpentIncorrect'])) / denom_i
        # AvgTime_NA
        denom_na = prev_na + new_na
        if denom_na > 0:
            user_dashboard['Total Question Solved']['QA']['AvgTime_NA'] = ((prev_na * user_dashboard['Total Question Solved']['QA']['AvgTime_NA']) + (new_na * data['sections']['QA']['timeSpentUnattempted'])) / denom_na

        topics = list(data['sections']['QA']['topics'].keys())
        print(topics)

        for sdq in topics:
            E_C = user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['E']['C']
            E_I = user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['E']['I']
            E_NA = user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['E']['NA']
            M_C = user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['M']['C']
            M_I = user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['M']['I']
            M_NA = user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['M']['NA']
            H_C = user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['H']['C']
            H_I = user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['H']['I']
            H_NA = user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['H']['NA']

            user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['E']['C'] = [E_C[0] + data['sections']['QA']['topics'][sdq]['easyCorrect'] , E_C[1] + data['sections']['QA']['topics'][sdq]['easyCorrectTotalTime']]
            user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['E']['I'] = [E_I[0] + data['sections']['QA']['topics'][sdq]['easyIncorrect'] , E_I[1] + data['sections']['QA']['topics'][sdq]['easyIncorrectTotalTime']]
            user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['E']['NA'] = [E_NA[0] + data['sections']['QA']['topics'][sdq]['easyNA'] , E_NA[1] + data['sections']['QA']['topics'][sdq]['easyNATotalTime']]
            user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['M']['C'] = [M_C[0] + data['sections']['QA']['topics'][sdq]['mediumCorrect'] , M_C[1] + data['sections']['QA']['topics'][sdq]['mediumCorrectTotalTime']]
            user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['M']['I'] = [M_I[0] + data['sections']['QA']['topics'][sdq]['mediumIncorrect'] , M_I[1] + data['sections']['QA']['topics'][sdq]['mediumIncorrectTotalTime']]
            user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['M']['NA'] = [M_NA[0] + data['sections']['QA']['topics'][sdq]['mediumNA'] , M_NA[1] + data['sections']['QA']['topics'][sdq]['mediumNATotalTime']]
            user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['H']['C'] = [H_C[0] + data['sections']['QA']['topics'][sdq]['hardCorrect'] , H_C[1] + data['sections']['QA']['topics'][sdq]['hardCorrectTotalTime']]
            user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['H']['I'] = [H_I[0] + data['sections']['QA']['topics'][sdq]['hardIncorrect'] , H_I[1] + data['sections']['QA']['topics'][sdq]['hardIncorrectTotalTime']]
            user_dashboard['Total Question Solved']['QA']['section_breakdown'][sdq]['H']['NA'] = [H_NA[0] + data['sections']['QA']['topics'][sdq]['hardNA'] , H_NA[1] + data['sections']['QA']['topics']['Arithmetic - Part 1']['hardNATotalTime']]

    #print(user_dashboard)
    user.update_one({"email": current_user}, {"$set": {"dashboardAnalytics": user_dashboard}})
    print("--------------------------------")
    print({"message": "Test uploaded successfully"})
    print("--------------------------------")
    return {"message": "Test uploaded successfully" , "id": str(test_id.inserted_id)}


@router.post("/getquestiondata")
async def get_question_data(request: Request, current_user: str = Depends(verify_token)):
    data = await request.json()
    found_user = user.find_one({"email": current_user})
    if not found_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    VARCqueslist = data.get("VARCqueslist", [])
    DILRqueslist = data.get("DILRqueslist", [])
    QAqueslist = data.get("QAqueslist", [])
    print(VARCqueslist, DILRqueslist, QAqueslist)
    VARCques = []
    DILRques = []
    QAques = []
    if VARCqueslist:
        ids = [ObjectId(i) for i in VARCqueslist]
        VARCq = VARCquestion.find({"_id": {"$in": ids}})
        for t in VARCq:
            t['_id'] = str(t['_id'])
            VARCques.append(t)
    if DILRqueslist:
        ids = [ObjectId(i) for i in DILRqueslist]
        DILRq = DILRquestion.find({"_id": {"$in": ids}})
        for t in DILRq:
            t['_id'] = str(t['_id'])
            DILRques.append(t)
    if QAqueslist:
        ids = [ObjectId(i) for i in QAqueslist]
        QAq = QAquestion.find({"_id": {"$in": ids}})
        for t in QAq:
            t['_id'] = str(t['_id'])
            QAques.append(t)
    #print({"VARCques": VARCques, "DILRques": DILRques, "QAques": QAques})
    return {"VARCques": VARCques, "DILRques": DILRques, "QAques": QAques}