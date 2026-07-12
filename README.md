# MachineLearningBD

Do an machine learning du bao va uoc luong xam nhap man tai Dong bang song Cuu Long.

## Cau truc thu muc

- `Data/`: du lieu tho, du lieu da tien xu ly va cac bao cao chat luong du lieu.
- `src/`: ma nguon chinh cua cac mo hinh.
  - `src/src_lstm/`: pipeline tien xu ly, EDA, train va evaluate cho LSTM/MS-LSTM.
- `gee_scripts/`: script Google Earth Engine de trich xuat du lieu ve tinh/thoi tiet.
- `models/`: checkpoint, metrics, predictions va bao cao ket qua mo hinh.
- `Literature Review/`: cac paper va tai lieu tham khao.
- `Proposal_v2_XamNhapMan_DBSCL.pdf`: proposal cua de tai.

## Luu y khi lam viec nhom

Khong commit moi truong ao, cache Python, file tam cua he dieu hanh hoac file khoa cua Excel. Cac thanh vien nen tao branch rieng cho phan viec cua minh, vi du:

```bash
git checkout -b feature/xgboost
```

Sau khi hoan thanh mot phan viec:

```bash
git status
git add .
git commit -m "Add XGBoost preprocessing pipeline"
git push origin feature/xgboost
```

## LSTM

Phan LSTM hien nam trong `src/src_lstm/`. Ket qua, checkpoint, metrics va bao cao mo hinh nam trong `models/lstm/`.
