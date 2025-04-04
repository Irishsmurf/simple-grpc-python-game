To build Python Protos:

```shell
python -m grpc_tools.protoc --proto_path=proto \                                                                                                                                                                                                                               ─╯
                            --python_out=./gen/python \
                            --pyi_out=./gen/python \
                            --grpc_python_out=./gen/python \
                            proto/game.proto
```

---

Build GoLang Protos:

```shell
❯ protoc --proto_path=proto \                                                                                                                                                                                                                                                    ─╯
       --go_out=./gen/go/game --go_opt=paths=source_relative \
       --go-grpc_out=./gen/go/game --go-grpc_opt=paths=source_relative \
       proto/game.proto
```