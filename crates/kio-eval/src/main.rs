mod app;

use clap::Parser;
use kio_core::ExitCode;
use kio_eval::generator::GeneratorError;

fn main() {
    let args = app::Args::parse();
    let code = match app::run(args) {
        Ok(code) => code,
        // Keep the generator's stable user-facing overwrite contract.
        Err(app::AppError::Generator(GeneratorError::NonEmpty(path))) => {
            eprintln!(
                "[error] 出力先が空でない: {} (--force で上書き)",
                path.display()
            );
            ExitCode::Failure
        }
        Err(error) => {
            eprintln!("kio-eval: {error}");
            ExitCode::Failure
        }
    };
    // Evaluator policy intentionally reserves 2 for NOT-IMPLEMENTED, while
    // Kio's product ExitCode::InvalidUsage also happens to be 2.
    std::process::exit(code.code());
}
