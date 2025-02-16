# Backend_Red_Panda

## 和前端串通

###文档处理

开启后台
```bash
python -m api.server
```

传入pdf

```bash
curl -X POST -F "file=@/Users/jiadengxu/Documents/Proposal.pdf" http://localhost:5001/ingest
```

检查文本向量

```bash
curl http://localhost:5001/vector-stats
```