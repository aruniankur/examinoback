from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import List, Optional, Union
from routes.database import passage,DILRquestion,VARCquestion,QAquestion, user
from routes.auth import verify_token
import random
import os

router = APIRouter(prefix="/questions", tags=["questions"])

# Pydantic models for request/response
class QuestionRequest(BaseModel):
    num_questions: int
    difficulty: str
    section: list[str]

class Option(BaseModel):
    key: str
    text: str

class Question(BaseModel):
    question_id: int
    question_text: str
    question_image_url: Optional[str] = None
    typeanswer: bool = False
    option: Optional[List[Option]] = None

class PassageQuestion(BaseModel):
    question_id: int
    question_text: str
    typeanswer: bool = False
    option: Optional[List[Option]] = None

class Passage(BaseModel):
    passageid: int
    passagetitle: str
    passage: str
    passage_image_url: Optional[str] = None
    question: List[PassageQuestion]

class QuestionResponse(BaseModel):
    questions: List[Union[Question, Passage]]

def ensure_list(x):
    if isinstance(x, list):
        return x
    return [x]

# Question generation functions
def getQAquestion(num,areas,diff = "Med"):
    if not isinstance(areas, list):
        areas = [areas]
    areas = [a.strip() for a in areas if a]
    t = diff[0].upper()
    if t not in ["E","M","H"]:
        t = "M"
    query = {
        "difficulty": t,           # filter by difficulty
        "Domain": {"$in": areas},       # Domain must not be empty
    }
    random_docs = list(
        QAquestion.aggregate([
            {"$match": query},
            {"$sample": {"size": num}}
        ])
    )
    random_docs = ensure_list(random_docs)
    for i in range(len(random_docs)):
        random_docs[i]['_id'] = str(random_docs[i]['_id'])
    return random_docs

def make_dilr_sets(n):
    if n < 4:
        return []
    result = []
    remaining = n
    while remaining > 0:
        if remaining % 5 == 0:
            result.append(5)
            remaining -= 5
        elif remaining % 4 == 0:
            result.append(4)
            remaining -= 4
        else:
            if remaining > 5:
                choice = random.choice([4, 5])
            else:
                choice = remaining
            result.append(choice)
            remaining -= choice
    return result

def fill_list(items, n):
    if not items:
        return []
    if len(items) >= n:
        return random.sample(items, n)   # no repeats
    else:
        return random.choices(items, k=n)  # allow repeats

def get_docs_with_duplicates(collection, ids):
    unique_ids = list(set(ids))
    docs = list(collection.find({"_id": {"$in": unique_ids}}))
    lookup = {str(doc["_id"]): doc for doc in docs}
    result = [lookup[str(_id)] for _id in ids if str(_id) in lookup]
    return result

def getDILRquestion(number,area,diff = "Med"):
    if area == []:
        return []
    t = diff[0].upper()
    if t not in ["E","M","H"]:
        t = "M"
    qw = make_dilr_sets(number)
    e = len(qw)
    query = {
        "section":"DILR",
        "Domain": {"$in": area},
    }
    random_docs = list(passage.aggregate([
            {"$match": query},
            {"$sample": {"size": e}}
        ])
    )
    random_docs = ensure_list(random_docs)
    for i in range(e):
        print(random_docs[i]['question_id'][t])
        ques = fill_list(random_docs[i]['question_id'][t],qw[i])
        print(ques)
        random_docs[i]["_id"] = str(random_docs[i]["_id"])
        question = get_docs_with_duplicates(DILRquestion,ques)
        for j in range(qw[i]):
            question[j]["_id"] = str(question[j]["_id"])
        random_docs[i]['question'] = question
        random_docs[i].pop("question_id", None)
    return random_docs
        

# Routes
@router.post("/qa")
async def create_qa_questions(request: QuestionRequest, current_user: str = Depends(verify_token)):
    print(request)
    try:
        if request.num_questions <= 0 or request.num_questions > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Number of questions must be between 1 and 50"
            )
        
        if request.difficulty not in ["easy", "medium", "hard"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Difficulty must be 'easy', 'medium', or 'hard'"
            )
        
        questions = getQAquestion(request.num_questions,request.section ,request.difficulty)
        #print(questions)
        return questions
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating QA questions: {str(e)}"
        )


def byfour(n):
    if n >= 16:
        return 16,n-16
    r = n%4
    q = n//4
    return q,r



def divideRC(num):
    lst = []
    while num > 4:
        lst.append(4)
        num = num - 4
    if num > 0 : lst.append(num)
    return lst

def getVAques(num, diff = "Med"):
    t = diff[0].upper()
    if t not in ["E","M","H"]:
        t = "M"
    query = {
    "difficulty": t,
    "Domain" : "Verbal Ability"# filter by difficulty
    }
    random_docs = list(
        VARCquestion.aggregate([
            {"$match": query},
            {"$sample": {"size": num}}
        ])
    )
    random_docs = ensure_list(random_docs)
    for i in random_docs:
        i['_id'] = str(i['_id'])
    return random_docs

def getRCques(num,diff="med"):
    d = diff[0].upper()
    if d not in ["E","M","H"]:
        d = "M"
    query = {"section":"VARC",}
    lst = divideRC(num)
    tp = len(lst)
    random_docs = list(passage.aggregate([
                {"$match": query},
                {"$sample": {"size": tp}}
            ])
        )
    random_docs = ensure_list(random_docs)
    for i in range(len(random_docs)):
        print(random_docs[i]['question_id'][d])
        quesid = fill_list(random_docs[i]['question_id'][d],lst[i])
        random_docs[i]["_id"] = str(random_docs[i]["_id"])
        question = get_docs_with_duplicates(VARCquestion,quesid)
        for j in range(lst[i]):
            question[j]["_id"] = str(question[j]["_id"])
        random_docs[i]['question'] = question
        random_docs[i].pop("question_id", None)
    return random_docs


@router.post("/varc")
async def create_varc_questions(request: QuestionRequest, current_user: str = Depends(verify_token)):
    print("varc")
    print(request)
    try:
        if request.num_questions <= 0 or request.num_questions > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Number of questions must be between 1 and 50"
            )
        
        if request.difficulty not in ["easy", "medium", "hard"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Difficulty must be 'easy', 'medium', or 'hard'"
            )
        
        print(request.section)
        if len(request.section) == 2:
            v,l = byfour(request.num_questions)
            print(v,l)
            verbal = getVAques(l,request.difficulty)
            reading = getRCques(request.num_questions-l,request.difficulty)
            questions = {"reading":reading,"verbal":verbal}
            #print(questions)
            return questions
        else:
            if request.section[0] == "Verbal Ability":
                questions = getVAques(request.num_questions, request.difficulty)
                return {"verbal":questions}
            else:
                questions = getRCques(request.num_questions, request.difficulty)
                return {"reading":questions}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating VARC questions: {str(e)}"
        )

@router.post("/dilr")
async def create_dilr_questions(request: QuestionRequest, current_user: str = Depends(verify_token)):
    print("dilr")
    print(request)
    try:
        if request.num_questions <= 0 or request.num_questions > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Number of questions must be between 1 and 50"
            )
        if request.difficulty not in ["easy", "medium", "hard"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Difficulty must be 'easy', 'medium', or 'hard'"
            )
        questions = getDILRquestion(request.num_questions,request.section, request.difficulty)
        #print(questions)
        return questions
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating DILR questions: {str(e)}"
        )


from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

API_KEY=os.getenv("API_KEY","None")
MODEL=os.getenv("MODEL","None")

llm = ChatGoogleGenerativeAI(model=MODEL, api_key=SecretStr(API_KEY) if API_KEY else None, temperature=0.7)

class AIQuestionResponseRequest(BaseModel):
    questionid: str
    section: str

@router.post("/aiquestionresponse")
async def aiquestionresponse(request: AIQuestionResponseRequest, current_user: str = Depends(verify_token)):
    print(request)
    try:
        user_doc = user.find_one({"email": current_user})
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        if request.section=="QA":
            question = QAquestion.find_one({"question_id": request.questionid})
        elif request.section=="VARC":
            question = VARCquestion.find_one({"question_id": request.questionid})
        elif request.section=="DILR":
            question = DILRquestion.find_one({"question_id": request.questionid})
        
        response = llm.invoke("how will you prove the value of pi is 3.14 , using a mathematical proof")
        return {"status": "ok" , "response": response.content}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating AI question response: {str(e)}"
        )