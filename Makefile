BIN := terminator2
TARGET := target/release/$(BIN)

.PHONY: all release debug run clean

all: $(BIN)

test:
	xvfb-run -a -s "-screen 0 1920x1080x24" env REQUIRE_GUI=1 GDK_BACKEND=x11 LANG=C.UTF-8 cargo test -- --nocapture  > tr.txt 2>&1

$(BIN): release
	@cp $(TARGET) $(BIN)

release:
	@cargo build --release

debug:
	@cargo build

run:
	@cargo run

clean:
	@cargo clean
	@rm -f $(BIN)
