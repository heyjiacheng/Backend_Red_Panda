# Backend_Red_Panda

## 环境安装

从[官网](https://ollama.com/)安装Ollama。
再下载所需模型（可在.env中替换）：
```bash
# 下载语言模型
ollama run deepseek-r1:1.5b
# 下载文本嵌入模型
ollama pull nomic-embed-text
```
克隆项目：
```bash
git clone https://github.com/heyjiacheng/Backend_Red_Panda.git
cd Backend_Red_Panda
```
安装依赖包：
```bash
pip install -r requirements.txt
```
开启后台
```bash
python3 app.py
```

## API 接口文档

### 知识库管理

#### 创建知识库

```bash
curl --request POST \
  --url http://localhost:8080/knowledge-bases \
  --header 'Content-Type: application/json' \
  --data '{"name": "研究论文", "description": "我的研究论文集合"}'
```

#### 列出所有知识库

```bash
curl --request GET \
  --url http://localhost:8080/knowledge-bases
```

#### 获取单个知识库详情

```bash
curl --request GET \
  --url http://localhost:8080/knowledge-bases/1
```

#### 更新知识库

```bash
curl --request PUT \
  --url http://localhost:8080/knowledge-bases/1 \
  --header 'Content-Type: application/json' \
  --data '{"name": "更新的名称", "description": "更新的描述"}'
```

#### 删除知识库

```bash
curl --request DELETE \
  --url http://localhost:8080/knowledge-bases/1
```

### 文档处理

#### 上传文档

```bash
# 上传到指定知识库（2 号知识库）
curl -X POST http://localhost:8080/upload/2 -F file=@/Users/jiadengxu/Documents/3d_gaussian_splatting_low.pdf
```

#### 列出所有文档

```bash
# 列出所有文档
curl --request GET \
  --url http://localhost:8080/documents

```

#### 获取文档详情（单个文档）
```bash
curl --request GET \
  --url http://localhost:8080/documents/1
```

#### 下载文档

```bash
curl --request GET \
  --url http://localhost:8080/documents/1/download \
  --output downloaded_document.pdf
```

#### 删除文档

```bash
curl --request DELETE \
  --url http://localhost:8080/documents/1
```

### 查询功能

#### 提问

```bash
# 在所有知识库中查询
curl --request POST \
  --url http://localhost:8080/query \
  --header 'Content-Type: application/json' \
  --data '{ "query": "What technique used here for 3D scene reconstruction?" }'

# 在特定知识库中查询
curl -X POST \         
  http://localhost:8080/query \          
  -H "Content-Type: application/json" \
  -d '{"query": "What 3D reconstruction techniques are used in this research?", "knowledge_base_id": 2}'
```