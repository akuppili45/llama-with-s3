import os
from llama_index import SimpleDirectoryReader, VectorStoreIndex, StorageContext, ServiceContext, load_index_from_storage, download_loader
from flask import Flask, request, make_response, jsonify
import boto3
import s3fs
from s3reader import S3DirectoryReader
from flask_cors import CORS
from werkzeug.utils import secure_filename
import json

# NOTE: for local testing only, do NOT deploy with your key hardcoded
# os.environ['OPENAI_API_KEY'] = "<KEY>"

index = None
app = Flask(__name__)
CORS(app)

s3 = boto3.resource('s3')
s3_client = boto3.client('s3')
bucket = s3.Bucket('llm-indices-1')

s3filesys = s3fs.S3FileSystem(
   anon=False
)
stored_docs = {}
# for obj in bucket.objects.filter(Prefix='documents/'):
#     idx = obj.key.index('/')
#     print(obj.key[idx + 1:])
    # print(obj.key[obj.key.find('documents/') + len(obj.key):])

def IsObjectExists(path):
    for object_summary in bucket.objects.filter(Prefix=path):
        return True
    return False
def initialize_index():
    global index
    storage_context = StorageContext.from_defaults()
    service_context = ServiceContext.from_defaults(chunk_size_limit=512)
    print(IsObjectExists('storage_demo/'))
    if IsObjectExists('storage_demo/'):
        index = load_index_from_storage(StorageContext.from_defaults(persist_dir='llm-indices-1/storage_demo',fs=s3filesys), service_context=service_context)
    else:
        S3Reader = download_loader("S3Reader")
        loader = S3Reader(bucket='llm-indices-1', prefix='documents/')
        documents = loader.load_data()
        index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)
        index.set_index_id("vector_index")
        index.storage_context.persist('llm-indices-1/storage_demo', fs=s3filesys)

@app.route("/query", methods=["GET"])
def query_index():
    global index
    query_text = request.args.get("text", None)
    if query_text is None:
        return "No text found, please include a ?text=blah parameter in the URL", 400
    query_engine = index.as_query_engine()
    response = query_engine.query(query_text)
    response_json = {
        "text": str(response),
        "sources": [{"text": str(x.source_text), 
                     "similarity": round(x.similarity, 2),
                     "doc_id": str(x.doc_id),
                     "start": x.node_info['start'],
                     "end": x.node_info['end']
                    } for x in response.source_nodes]
    }
    return make_response(jsonify(response_json)), 200

@app.route("/getDocuments", methods=["GET"])
def get_documents():
    document_list = []
    for obj in bucket.objects.filter(Prefix='documents/'):
        idx = obj.key.index('/')
        document_list.append(obj.key[idx + 1:])
    print(document_list)
    return make_response(jsonify(document_list)), 200
    # return []

@app.route("/uploadFile", methods=["GET","POST"])
def uploadFile():
    if 'file' not in request.files:
        return "Please send a POST request with a file", 400
    filepath = None

    try:
        uploaded_file = request.files["file"]
        uploaded_file.filename = secure_filename(uploaded_file.filename)
        print("before file upload", flush=True)
        s3_client.upload_fileobj(uploaded_file, 'llm-indices-1', 'documents/'+ uploaded_file.filename, ExtraArgs={
            "ContentType": uploaded_file.content_type    #Set appropriate content type as per the file
        })
        print("after file upload", flush=True)
        # filepath = os.path.join('documents', os.path.basename(uploaded_file.filename))
        # print(type(filepath))
        # print(filepath)
        # # uploaded_file.save(filepath)
        # # put into s3 documents/
        
        if request.form.get("filename_as_doc_id", None) is not None:
            print('not none')
            insert_into_index('documents/'+ uploaded_file.filename, doc_id=uploaded_file.filename)
        else:
            insert_into_index('documents/'+ uploaded_file.filename)
    except Exception as e:
        print(e)
        # cleanup temp file
        if filepath is not None and os.path.exists(filepath):
            os.remove(filepath)
        return "Error: {}".format(str(e)), 500
    return "File inserted!", 200
    
def insert_into_index(doc_file_path, doc_id=None):
    global index, stored_docs
    S3Reader = download_loader("S3Reader")
    # print(doc_file_path)
    loader = S3Reader(bucket='llm-indices-1', key=doc_file_path)
    document = loader.load_data()[0]
    if doc_id is not None:
        document.doc_id = doc_id
    
    stored_docs[document.doc_id] = document.text[0:200]
    index.insert(document)
    index.storage_context.persist('llm-indices-1/storage_demo', fs=s3filesys)


if __name__ == "__main__":
    print("running")
    initialize_index()
    app.run(host="0.0.0.0", port=5601)
