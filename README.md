# Backend_Red_Panda

## 环境安装

安装依赖包：
```bash
pip install -r requirements.txt
```

开启后台
```bash
python3 app.py
```

## 和前端串通

### 文档处理

传入pdf

```bash
curl --request POST \
  --url http://localhost:8080/embed \
  --header 'Content-Type: multipart/form-data' \
  --form file=@/Users/jiadengxu/Documents/Proposal.pdf
```

提问

```bash
curl --request POST \
  --url http://localhost:8080/query \
  --header 'Content-Type: application/json' \
  --data '{ "query": "What technique used here for 3D scene reconstruction?" }'
```