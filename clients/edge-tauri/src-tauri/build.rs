fn main() {
    // Generate gRPC client from the proto definition.
    // Requires: protoc (brew install protobuf / apt install protobuf-compiler)
    //           cargo install protoc-gen-prost protoc-gen-tonic
    //           OR: cargo add tonic-build to [build-dependencies] and call:
    tonic_build::configure()
        .build_server(false) // client-only for Tauri app
        .out_dir("src/proto_gen")
        .compile_protos(&["../proto/edge_push.proto"], &["../proto"])
        .expect("failed to compile proto — is protoc installed?");

    tauri_build::build();
}
