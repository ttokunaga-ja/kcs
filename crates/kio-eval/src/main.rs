mod app;

use clap::Parser;
use kio_core::ExitCode;

fn main() {
    let args = app::Args::parse();
    let code = match app::run(args) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("kio-eval: {error}");
            ExitCode::Failure
        }
    };
    // Evaluator policy intentionally reserves 2 for NOT-IMPLEMENTED, while
    // Kio's product ExitCode::InvalidUsage also happens to be 2.
    std::process::exit(code.code());
}
