import click

from cellphonedb.flask_terminal_query_launcher import FlaskTerminalQueryLauncher


@click.command()
@click.argument('meta-filename')
@click.argument('counts-filename')
@click.option('--iterations', default=1000, help='Number of pvalues analysis iterations [1000]')
@click.option('--data-path', default='', help='Directory where is allocated input data [in]')
@click.option('--output-path', default='',
              help='Directory where the results will be allocated (the directory must exist) [out]')
@click.option('--means-result-name', default='means.txt', help='Means result namefile [means.txt]')
@click.option('--pvalues-result-name', default='pvalues.txt', help='Pvalues result namefile [pvalues.txt]')
@click.option('--significant-mean-result-name', default='significant_means.txt',
              help='Significant result namefile [significant_means.txt]')
@click.option('--means-pvalues-result-name', default='pvalues_means.txt',
              help='Pvalues-means result namefile [pvalues_means.txt]')
@click.option('--deconvoluted-result-name', default='deconvoluted.txt',
              help='Deconvoluted result namefile [deconvoluted.txt]')
@click.option('--debug-seed', default='-1', help='Debug random seed 0 for disable it. >=0 to set it [-1]')
def cluster_statistical_analysis(meta_filename: str,
                                 counts_filename: str,
                                 iterations: str,
                                 data_path: str,
                                 output_path: str,
                                 means_result_name: str,
                                 pvalues_result_name: str,
                                 significant_mean_result_name: str,
                                 means_pvalues_result_name: str,
                                 deconvoluted_result_name: str,
                                 debug_seed: str):
    getattr(FlaskTerminalQueryLauncher(), 'cluster_statistical_analysis')(meta_filename,
                                                                          counts_filename,
                                                                          iterations, data_path,
                                                                          output_path,
                                                                          means_result_name,
                                                                          pvalues_result_name,
                                                                          significant_mean_result_name,
                                                                          means_pvalues_result_name,
                                                                          deconvoluted_result_name,
                                                                          debug_seed)