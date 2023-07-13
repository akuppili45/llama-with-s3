import os
from llama_index import SimpleDirectoryReader, VectorStoreIndex, StorageContext, ServiceContext, load_index_from_storage
from flask import Flask, request
import boto3
# NOTE: for local testing only, do NOT deploy with your key hardcoded
# os.environ['OPENAI_API_KEY'] = "<KEY>"

index = None
app = Flask(__name__)
index_dir = "./Index"


client = boto3.client('s3')
response = client.list_objects_v2(Bucket="llm-indices-1", Delimiter="/")
print([x['Prefix'] for x in response['CommonPrefixes']])
root_obj_names = [x['Prefix'] for x in response['CommonPrefixes']]
def initialize_index():
    global index
    storage_context = StorageContext.from_defaults()
    service_context = ServiceContext.from_defaults(chunk_size_limit=512)
    if os.path.exists(index_dir):
        index = load_index_from_storage(StorageContext.from_defaults(persist_dir=index_dir), service_context=service_context)
    else:
        documents = SimpleDirectoryReader("./documents").load_data()
        index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)
        storage_context.persist(index_dir)

@app.route("/query", methods=["GET"])
def query_index():
    global index
    query_text = request.args.get("text", None)
    if query_text is None:
        return "No text found, please include a ?text=blah parameter in the URL", 400
    query_engine = index.as_query_engine()
    response = query_engine.query(query_text)
    return str(response), 200


if __name__ == "__main__":
    initialize_index()
    app.run(host="0.0.0.0", port=5601)